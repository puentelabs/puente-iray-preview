#include "RenderTools.h"
#include "WorkerRuntime.h"
#include <dzapp.h>
#include <dzscene.h>
#include <dzrendermgr.h>
#include <dzrenderoptions.h>
#include <dzrenderer.h>
#include <dzimagerenderhandler.h>
#include <QtCore/QDateTime>
#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonArray>
#include <QtCore/QCoreApplication>
#include <QtCore/QProcess>
#include <QtCore/QSettings>
#include <QtCore/QTimer>
#include <QtCore/QUuid>
#include <QtGui/QDesktopServices>
#include <QtCore/QUrl>
#include <QtWidgets/QCheckBox>
#include <QtWidgets/QComboBox>
#include <QtWidgets/QDoubleSpinBox>
#include <QtWidgets/QFileDialog>
#include <QtWidgets/QFormLayout>
#include <QtWidgets/QLabel>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QVBoxLayout>
#ifdef Q_OS_WIN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <Windows.h>
#endif

RenderTools::RenderTools(QWidget *parent, QLineEdit *p, QLineEdit *root, QLineEdit *nr,
                        std::function<QJsonObject()> settings, std::function<void()> stop)
    : QWidget(parent), python(p), project(root), runtime(nr), controls(settings), stopPreview(stop) {
    auto *layout = new QVBoxLayout(this);
    auto *intro = new QLabel("Process a finished render, or render the current frame and process it. Results are saved in a new Puente folder.", this);
    intro->setWordWrap(true); layout->addWidget(intro);
    auto *form = new QFormLayout;
    scale = new QComboBox(this); scale->addItem("1x (enhancement only)", 1); scale->addItem("2x", 2); scale->addItem("4x", 4); scale->setCurrentIndex(1);
    method = new QComboBox(this); method->addItem("Lanczos (resize baseline)", "lanczos"); method->addItem("Real-ESRGAN (experimental)", "realesrgan");
    strength = new QDoubleSpinBox(this); strength->setRange(0, 1); strength->setSingleStep(0.05); strength->setValue(0.5);
    QSettings local("Puente Labs", "Iray Neural Preview");
    gpuPython = new QLineEdit(local.value("renderPython", p->text()).toString(), this);
    form->addRow("Output scale", scale); form->addRow("Upscaler", method); form->addRow("Neural upscale blend", strength);
    form->addRow("GPU Python", gpuPython); layout->addLayout(form);
    if (PuenteWorker::isPackaged(project->text())) {
        gpuPython->setText(PuenteWorker::executable(project->text()));
        form->setRowVisible(gpuPython, false);
    }
    gpuPython->setToolTip("CUDA PyTorch + spandrel executable, used for Real-ESRGAN. Lanczos uses the Python in Local setup.");
    connect(gpuPython, &QLineEdit::editingFinished, this, [this] {
        QSettings local("Puente Labs", "Iray Neural Preview"); local.setValue("renderPython", gpuPython->text().trimmed());
    });
    enhance = new QCheckBox("Apply enhancement controls from Preview tab", this); enhance->setChecked(true);
    reduced = new QCheckBox("Render at 1/scale resolution (experimental speed option)", this);
    automatic = new QCheckBox("Process successful single-frame Iray renders saved directly to file", this);
    automatic->setToolTip("For ordinary Render: choose Direct to File and a single frame. The original stays unchanged. Render-window-only output can be saved and processed with Process image.");
    layout->addWidget(enhance); layout->addWidget(reduced); layout->addWidget(automatic);
    auto *quality = new QLabel("Upscaling cannot guarantee the quality of a native high-resolution render. Compare faces, fine hair and textures. PNG/TIFF 8-bit sRGB only; output up to 32 MP and 8192 pixels per side.", this);
    quality->setWordWrap(true); layout->addWidget(quality);
    auto *buttons = new QHBoxLayout;
    renderButton = new QPushButton("Render + process...", this); fileButton = new QPushButton("Process image...", this);
    buttons->addWidget(renderButton); buttons->addWidget(fileButton); layout->addLayout(buttons);
    auto *second = new QHBoxLayout;
    cancelButton = new QPushButton("Cancel processing", this); openButton = new QPushButton("Open results", this);
    second->addWidget(cancelButton); second->addWidget(openButton); layout->addLayout(second);
    status = new QLabel("Ready for a finished render", this); status->setWordWrap(true); layout->addWidget(status); layout->addStretch();
    worker = new QProcess(this); deadline = new QTimer(this); deadline->setSingleShot(true);
#ifdef Q_OS_WIN
    worker->setCreateProcessArgumentsModifier([](QProcess::CreateProcessArguments *args) { args->flags |= CREATE_NO_WINDOW; });
#endif
    connect(deadline, &QTimer::timeout, this, [this] { cancel(); status->setText("Processing exceeded 30 minutes and was stopped."); });
    connect(worker, &QProcess::readyReadStandardOutput, this, [this] {
        while (worker->canReadLine()) status->setText(QString::fromUtf8(worker->readLine()).trimmed());
    });
    connect(worker, &QProcess::readyReadStandardError, this, [this] {
        QByteArray message = worker->readAllStandardError(); if (!message.isEmpty()) status->setText(QString::fromUtf8(message.right(2048)));
    });
    connect(worker, &QProcess::finished, this, [this](int code, QProcess::ExitStatus exit) {
        deadline->stop();
        QFile report(outputFolder + "/report.json"); QJsonObject result;
        if (report.open(QIODevice::ReadOnly)) result = QJsonDocument::fromJson(report.readAll()).object();
        if (exit == QProcess::NormalExit && code == 0 && result["status"].toString() == "passed") {
            ++completed; status->setText(QString("Saved %1 x %2 in %3").arg(result["output_size"].toArray()[0].toInt()).arg(result["output_size"].toArray()[1].toInt()).arg(QDir::toNativeSeparators(outputFolder)));
        } else { status->setText("Processing stopped: " + result["error"].toString(QString("worker exit %1; partial files kept in %2").arg(code).arg(outputFolder))); }
        updateEnabled();
    });
    connect(worker, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) { deadline->stop(); status->setText(worker->errorString()); updateEnabled(); }
    });
    connect(cancelButton, &QPushButton::clicked, this, &RenderTools::cancel);
    connect(openButton, &QPushButton::clicked, this, [this] { if (!outputFolder.isEmpty()) QDesktopServices::openUrl(QUrl::fromLocalFile(outputFolder)); });
    connect(fileButton, &QPushButton::clicked, this, [this] {
        QString input = QFileDialog::getOpenFileName(this, "Choose finished Iray render", QString(), "8-bit PNG or TIFF (*.png *.tif *.tiff)");
        if (input.isEmpty()) return;
        QString output = newOutputFolder(QFileInfo(input).absolutePath()); processFile(input, output);
    });
    connect(renderButton, &QPushButton::clicked, this, [this] {
        QString parent = QFileDialog::getExistingDirectory(this, "Choose folder for original and processed render");
        if (!parent.isEmpty()) renderTo(newOutputFolder(parent));
    });
    auto *mgr = dzApp->getRenderMgr();
    connect(mgr, &DzRenderMgr::renderStarting, this, &RenderTools::renderStarted);
    connect(mgr, &DzRenderMgr::renderFinished, this, &RenderTools::renderFinished);
    connect(method, &QComboBox::currentIndexChanged, this, &RenderTools::updateEnabled);
    connect(scale, &QComboBox::currentIndexChanged, this, &RenderTools::updateEnabled);
    updateEnabled();
}

RenderTools::~RenderTools() { cancel(); }
void RenderTools::cancel() {
    if (worker->state() != QProcess::NotRunning) { worker->kill(); worker->waitForFinished(1500); }
    deadline->stop(); updateEnabled();
}
void RenderTools::updateEnabled() {
    bool idle = !rendering && worker->state() == QProcess::NotRunning;
    renderButton->setEnabled(idle); fileButton->setEnabled(idle); cancelButton->setEnabled(worker->state() != QProcess::NotRunning);
    openButton->setEnabled(!outputFolder.isEmpty());
    bool neural = method->currentData().toString() == "realesrgan" && scale->currentData().toInt() > 1;
    strength->setEnabled(idle && neural); gpuPython->setEnabled(idle && neural);
    scale->setEnabled(idle); method->setEnabled(idle); enhance->setEnabled(idle); reduced->setEnabled(idle); automatic->setEnabled(idle);
}
QString RenderTools::newOutputFolder(const QString &parent) const {
    return QDir(parent).filePath("Puente-render-" + QDateTime::currentDateTime().toString("yyyyMMdd-HHmmss") + "-" + QUuid::createUuid().toString(QUuid::WithoutBraces).left(8));
}
QJsonObject RenderTools::jobFor(const QString &input, const QString &output) const {
    QJsonObject job;
    job["input"] = QFileInfo(input).absoluteFilePath(); job["output_dir"] = QFileInfo(output).absoluteFilePath();
    job["scale"] = scale->currentData().toInt(); job["method"] = method->currentData().toString();
    job["upscale_strength"] = strength->value(); job["enhance"] = enhance->isChecked(); job["controls"] = controls();
    job["runtime"] = QDir(runtime->text()).absolutePath(); job["model_dir"] = QDir(project->text()).absoluteFilePath("runtime/upscale");
    return job;
}
bool RenderTools::configure(int factor, const QString &backend, bool nr, double amount, bool smaller) {
    if (rendering || worker->state() != QProcess::NotRunning || !qIsFinite(amount) || amount < 0 || amount > 1) return false;
    int index = scale->findData(factor), backendIndex = method->findData(backend);
    if (index < 0 || backendIndex < 0) return false;
    scale->setCurrentIndex(index); method->setCurrentIndex(backendIndex); enhance->setChecked(nr); strength->setValue(amount); reduced->setChecked(smaller); return true;
}
void RenderTools::setAutomatic(bool enabled) { automatic->setChecked(enabled); }
bool RenderTools::configurePython(const QString &executable) {
    if (rendering || worker->state() != QProcess::NotRunning || !QFileInfo(executable.trimmed()).isFile()) return false;
    gpuPython->setText(executable.trimmed());
    QSettings local("Puente Labs", "Iray Neural Preview"); local.setValue("renderPython", gpuPython->text()); return true;
}
QVariantMap RenderTools::state() const {
    return {{"busy", rendering || worker->state() != QProcess::NotRunning}, {"rendering", rendering}, {"completed", completed},
            {"status", status->text()}, {"outputFolder", outputFolder}, {"workerPid", worker->processId()},
            {"scale", scale->currentData()}, {"method", method->currentData()}, {"automatic", automatic->isChecked()}, {"gpuPython", gpuPython->text()}};
}
bool RenderTools::processFile(const QString &input, const QString &directory) {
    if (rendering || worker->state() != QProcess::NotRunning) return false;
    QString suffix = QFileInfo(input).suffix().toLower();
    if (!QFileInfo(input).isFile() || (suffix != "png" && suffix != "tif" && suffix != "tiff")) { status->setText("Choose an existing PNG/TIFF render"); return false; }
    QString error = dependencyError(jobFor(input, directory)); if (!error.isEmpty()) { status->setText(error); return false; }
    if (QFileInfo::exists(directory) || !QDir().mkdir(directory)) { status->setText("Choose a new result folder inside an existing directory"); return false; }
    return launch(jobFor(input, directory));
}
bool RenderTools::launch(const QJsonObject &job) {
    QString root = QDir(project->text()).absolutePath();
    bool neural = job["method"].toString() == "realesrgan" && job["scale"].toInt() > 1 && job["upscale_strength"].toDouble() > 0;
    QString executable = (neural ? gpuPython->text() : python->text()).trimmed();
    QString error = dependencyError(job);
    if (!error.isEmpty()) { status->setText(error); return false; }
    if (worker->state() != QProcess::NotRunning) return false;
    stopPreview(); // Release preview GPU allocations before processing a render.
    outputFolder = job["output_dir"].toString();
    QFile file(outputFolder + "/request.json");
    if (!file.open(QIODevice::WriteOnly | QIODevice::NewOnly)) { status->setText("Cannot create a new render request"); return false; }
    file.write(QJsonDocument(job).toJson()); file.close();
    QSettings local("Puente Labs", "Iray Neural Preview"); local.setValue("renderPython", gpuPython->text());
    worker->setWorkingDirectory(root);
    worker->start(PuenteWorker::isPackaged(root) ? PuenteWorker::executable(root) : executable,
        PuenteWorker::arguments(root, "render", {"--job", file.fileName(), "--parent-pid", QString::number(QCoreApplication::applicationPid())}));
    status->setText("Starting render processing..."); deadline->start(1800000); updateEnabled(); return true;
}
QString RenderTools::dependencyError(const QJsonObject &job) const {
    QString root = QDir(project->text()).absolutePath();
    bool neural = job["method"].toString() == "realesrgan" && job["scale"].toInt() > 1 && job["upscale_strength"].toDouble() > 0;
    if (PuenteWorker::isPackaged(root))
        return PuenteWorker::check(root, runtime->text(), job["enhance"].toBool(), neural, job["scale"].toInt());
    if (!QFileInfo(neural ? gpuPython->text() : python->text()).isFile() || !QFileInfo(root + "/render_worker.py").isFile())
        return "Check Local setup and GPU Python paths";
    if (job["enhance"].toBool() && (!QFileInfo(root + "/viewport_worker.py").isFile()
        || !QFileInfo(root + "/vendor/ComfyUI-DLSS5-NR/native/bin/dlss5nr_bridge.dll").isFile()
        || !QFileInfo(QDir(runtime->text()).filePath("nvngx_dlssnr.dll")).isFile()
        || !QFileInfo(QDir(runtime->text()).filePath("caller/nvngx.dll_comfy.dll")).isFile()))
        return "Enhancement dependencies are missing; check Local setup";
    if (neural && !QFileInfo(root + QString("/runtime/upscale/RealESRGAN_x%1plus.pth").arg(job["scale"].toInt())).isFile())
        return "Upscaling model missing; run bootstrap-upscale.ps1";
    // Check the selected interpreter itself before spending time on an Iray render.
    // find_spec avoids importing the GPU framework or loading model weights here.
    QProcess probe;
#ifdef Q_OS_WIN
    probe.setCreateProcessArgumentsModifier([](QProcess::CreateProcessArguments *args) { args->flags |= CREATE_NO_WINDOW; });
#endif
    QString executable = (neural ? gpuPython->text() : python->text()).trimmed();
    QString modules = neural ? "['numpy','PIL','torch','spandrel']" : "['numpy','PIL']";
    QString code = "import importlib.util,sys; missing=[m for m in " + modules
        + " if importlib.util.find_spec(m) is None]; print(', '.join(missing)); sys.exit(bool(missing))";
    probe.start(executable, {"-B", "-c", code});
    if (!probe.waitForFinished(5000)) { probe.kill(); probe.waitForFinished(1000); return "Python dependency check failed or timed out. Check the selected executable."; }
    if (probe.exitStatus() != QProcess::NormalExit || probe.exitCode() != 0) {
        QString missing = QString::fromUtf8(probe.readAllStandardOutput()).trimmed();
        return QString("%1 is missing %2. Set %3 to a Python with %4. Rendering has not started.")
            .arg(QDir::toNativeSeparators(executable), missing.isEmpty() ? "required packages" : missing,
                 neural ? "GPU Python" : "Local setup > Python", neural ? "CUDA PyTorch and spandrel" : "NumPy and Pillow");
    }
    return {};
}
bool RenderTools::renderTo(const QString &directory) {
    auto *mgr = dzApp->getRenderMgr(); auto *renderer = mgr->getActiveRenderer(); auto *options = mgr->getRenderOptions();
    if (rendering || worker->state() != QProcess::NotRunning || mgr->isRendering()) return false;
    if (!renderer || !renderer->getName().contains("Iray", Qt::CaseInsensitive) || !options->isCurrentFrameRender()) { status->setText("Choose NVIDIA Iray and a single current frame in Render Settings"); return false; }
    QJsonObject job = jobFor(directory + "/original.png", directory);
    QString error = dependencyError(job); if (!error.isEmpty()) { status->setText(error); return false; }
    if (QFileInfo::exists(directory) || !QDir().mkdir(directory)) { status->setText("Choose a new result folder inside an existing directory"); return false; }
    DzRenderOptions local; local.copyFrom(options);
    QSize size = local.getImageSize(); int factor = reduced->isChecked() ? scale->currentData().toInt() : 1;
    size = QSize(qMax(1, qRound(double(size.width()) / factor)), qMax(1, qRound(double(size.height()) / factor)));
    qint64 outputWidth = qint64(size.width()) * scale->currentData().toInt(), outputHeight = qint64(size.height()) * scale->currentData().toInt();
    if (qMax(outputWidth, outputHeight) > 8192 || outputWidth * outputHeight > 32 * 1024 * 1024
        || (enhance->isChecked() && qMax(size.width(), size.height()) > 4096)) { status->setText("Reduce output size or scale to fit the alpha limits"); return false; }
    local.setImageSize(size); local.setRenderViewport(false); local.setShowPreview(false); local.setRenderType(DzRenderOptions::Software);
    local.setRenderImgToId(DzRenderOptions::DirectToFile); local.setRenderImgFilename(job["input"].toString());
    DzImageRenderHandler handler(size, dzScene->getTime(), job["input"].toString(), QImage::Format_ARGB32);
    handler.setPostProcessOnRenderFinish(false); handler.setWriteToFile(true); handler.setCreateThumbnail(false);
    stopPreview(); ownRender = rendering = true; updateEnabled(); status->setText(QString("Iray rendering %1 x %2...").arg(size.width()).arg(size.height()));
    bool okay = mgr->doCustomRender(&handler, nullptr, &local);
    ownRender = rendering = false; updateEnabled();
    if (!okay || !QFileInfo(job["input"].toString()).isFile()) { status->setText("Render canceled or failed; processing skipped"); return false; }
    return launch(job);
}
void RenderTools::renderStarted() {
    if (ownRender) return;
    if (worker->state() != QProcess::NotRunning) cancel(); // A new Iray render takes GPU priority.
    stopPreview(); rendering = true; automaticSource.clear(); automaticJob = {}; updateEnabled();
    auto *mgr = dzApp->getRenderMgr(); auto *options = mgr->getRenderOptions(); auto *renderer = mgr->getActiveRenderer();
    if (!automatic->isChecked() || worker->state() != QProcess::NotRunning || !renderer
        || !renderer->getName().contains("Iray", Qt::CaseInsensitive) || !options->isCurrentFrameRender()
        || options->getRenderImgToId() != DzRenderOptions::DirectToFile) return;
    automaticSource = QFileInfo(options->getRenderImgFilename()).absoluteFilePath(); automaticStart = QDateTime::currentMSecsSinceEpoch();
    automaticJob = jobFor(automaticSource, newOutputFolder(QFileInfo(automaticSource).absolutePath()));
}
void RenderTools::renderFinished(bool succeeded) {
    if (ownRender) return;
    rendering = false; updateEnabled();
    if (automaticSource.isEmpty()) return;
    QJsonObject job = automaticJob; QString input = automaticSource; qint64 started = automaticStart; automaticSource.clear();
    if (!succeeded) { status->setText("Render canceled or failed; processing skipped"); return; }
    QTimer::singleShot(250, this, [this, job, input, started] {
        QFileInfo file(input);
        if (!file.isFile() || file.lastModified().toMSecsSinceEpoch() < started - 2000) { status->setText("No fresh render file found; use Process image after saving"); return; }
        if (worker->state() != QProcess::NotRunning || rendering) { status->setText("Processing busy; use Process image for the finished render"); return; }
        if (!QDir().mkdir(job["output_dir"].toString())) { status->setText("Cannot create result folder"); return; }
        launch(job);
    });
}
