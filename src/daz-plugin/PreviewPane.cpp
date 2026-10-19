// Puente Labs, MIT. Experimental Studio 6 viewport enhancement.
#include <dzplugin.h>
#include <dzversion.h>
#include <dzapp.h>
#include <dzpane.h>
#include <dzaction.h>
#include <dzmainwindow.h>
#include <dzviewportmgr.h>
#include <dzviewport.h>
#include <dz3dviewport.h>
#include <dzcamera.h>
#include <dzscene.h>
#include <dzdrawstyle.h>
#include <QtCore/QDir>
#include <QtCore/QElapsedTimer>
#include <QtCore/QEventLoop>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QPointer>
#include <QtCore/QProcess>
#include <QtCore/QSettings>
#include <QtCore/QTimer>
#include <QtCore/QUuid>
#include <QtGui/QHideEvent>
#include <QtGui/QMouseEvent>
#include <QtGui/QPainter>
#include <QtGui/QColorSpace>
#include <QtWidgets/QApplication>
#include <QtWidgets/QCheckBox>
#include <QtWidgets/QComboBox>
#include <QtWidgets/QDoubleSpinBox>
#include <QtWidgets/QFormLayout>
#include <QtWidgets/QFileDialog>
#include <QtWidgets/QGroupBox>
#include <QtWidgets/QLabel>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QSlider>
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QTabWidget>
#include "RenderTools.h"
#include "WorkerRuntime.h"
#include <QtCore/QStandardPaths>
#include <cstring>

class PreviewCanvas : public QWidget {
public:
    explicit PreviewCanvas(QWidget *parent) : QWidget(parent) { setMinimumSize(160, 120); }
    void setImage(const QImage &value) { image = value; update(); }
protected:
    void paintEvent(QPaintEvent *) override {
        QPainter painter(this); painter.fillRect(rect(), QColor(25, 25, 28));
        if (image.isNull()) {
            painter.setPen(QColor(175, 175, 180));
            painter.drawText(rect().adjusted(8, 8, -8, -8), Qt::AlignCenter | Qt::TextWordWrap, "Enhanced preview");
        } else {
            QSize fitted = image.size(); fitted.scale(size(), Qt::KeepAspectRatio);
            QRect target(QPoint((width() - fitted.width()) / 2, (height() - fitted.height()) / 2), fitted);
            painter.setRenderHint(QPainter::SmoothPixmapTransform); painter.drawImage(target, image);
        }
    }
private:
    QImage image;
};

class PreviewOverlay : public QWidget {
public:
    explicit PreviewOverlay(QWidget *parent) : QWidget(parent) {
        setAttribute(Qt::WA_TransparentForMouseEvents);
        setFocusPolicy(Qt::NoFocus); hide();
    }
    QImage image;
protected:
    void paintEvent(QPaintEvent *) override { QPainter(this).drawImage(rect(), image); }
};

class PuenteIrayPreviewPane : public DzPane {
    Q_OBJECT
public:
    PuenteIrayPreviewPane() : DzPane("PuenteIrayPreviewPane") {
        setLabel("Puente Iray Preview");
        auto *rootLayout = new QVBoxLayout(this);
        auto *setupButton = new QPushButton("Local setup...", this); rootLayout->addWidget(setupButton);
        setupGroup = new QGroupBox("Local dependencies", this);
        auto *setupForm = new QFormLayout(setupGroup);
        QSettings settings("Puente Labs", "Iray Neural Preview");
        python = new QLineEdit(settings.value("python").toString(), this);
        project = new QLineEdit(settings.value("project").toString(), this);
        runtime = new QLineEdit(settings.value("runtime").toString(), this);
        const QString packaged = PuenteWorker::packagedRoot();
        if (!packaged.isEmpty()) {
            project->setText(packaged); python->setText(PuenteWorker::executable(packaged));
            if (runtime->text().isEmpty()) runtime->setText(QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) + "/PuenteLabs/IrayPreview/runtime");
        }
        setupForm->addRow("Python", python); setupForm->addRow("Prototype", project);
        setupForm->addRow("Runtime", runtime); rootLayout->addWidget(setupGroup);
        if (!packaged.isEmpty()) {
            setupForm->setRowVisible(python, false); setupForm->setRowVisible(project, false);
            setupGroup->setTitle("Runtime NR aportado por el usuario");
            auto *browse = new QPushButton("Elegir carpeta de runtime NR...", this);
            setupForm->addRow(browse);
            connect(browse, &QPushButton::clicked, this, [this] {
                QString folder = QFileDialog::getExistingDirectory(this, "Carpeta de runtime NR", runtime->text());
                if (!folder.isEmpty()) runtime->setText(folder);
            });
            auto *importDll = new QPushButton("Importar DLL NR...", this);
            setupForm->addRow(importDll);
            connect(importDll, &QPushButton::clicked, this, [this] {
                if (process->state() != QProcess::NotRunning) { status->setText("Detén el preview antes de cambiar el runtime."); return; }
                QString source = QFileDialog::getOpenFileName(this, "Tu runtime NR compatible", QString(), "NVIDIA NR (nvngx_dlssnr.dll)");
                if (source.isEmpty()) return;
                importNrRuntime(source);
            });
        }
        setupGroup->setVisible(python->text().isEmpty() || project->text().isEmpty() || runtime->text().isEmpty()
            || (!packaged.isEmpty() && !QFileInfo(QDir(runtime->text()).filePath("nvngx_dlssnr.dll")).isFile()));
        connect(setupButton, &QPushButton::clicked, this, [this] { setupGroup->setVisible(!setupGroup->isVisible()); });
        tabs = new QTabWidget(this); rootLayout->addWidget(tabs, 1);
        auto *previewTab = new QWidget(tabs); tabs->addTab(previewTab, "Preview");
        auto *layout = new QVBoxLayout(previewTab);
        auto *intro = new QLabel("Enhance the active Iray viewport.", this);
        intro->setWordWrap(true); layout->addWidget(intro);
        auto *form = new QFormLayout;
        appearance = new QComboBox(this);
        appearance->addItem("Natural", 1); appearance->addItem("Cinematic", 2); appearance->addItem("Runtime default", 0);
        form->addRow("Appearance", appearance);
        blend = slider(form, "Enhanced blend", 0, 100, 100);
        tone = slider(form, "Tone", 0, 200, 0);
        structure = slider(form, "Structure", 0, 200, 100);
        skin = slider(form, "Skin (-1 = default)", -100, 200, -100);
        blend->setToolTip("0 shows the original preview; 1 shows the enhanced preview.");
        tone->setToolTip("Adjust the neural treatment of tone and lighting.");
        structure->setToolTip("Adjust the neural structure control. Compare fine detail against the original.");
        skin->setToolTip("Use -1 for the model default. Check likeness and skin detail when changing this.");
        layout->addLayout(form);
        autoMask = new QCheckBox("Automatic skin mask", this);
        live = new QCheckBox("Refresh while idle (once per second)", this);
        overlayOn = new QCheckBox("Show enhancement in viewport", this);
        live->setChecked(true); overlayOn->setChecked(true);
        layout->addWidget(autoMask); layout->addWidget(live); layout->addWidget(overlayOn);
        auto *presetRow = new QHBoxLayout;
        auto *detail = new QPushButton("Detail", this), *stronger = new QPushButton("Stronger", this);
        presetRow->addWidget(detail); presetRow->addWidget(stronger); layout->addLayout(presetRow);
        auto *buttonRow = new QHBoxLayout;
        start = new QPushButton("Start preview", this); stop = new QPushButton("Stop", this);
        enhance = new QPushButton("Refresh", this);
        buttonRow->addWidget(start); buttonRow->addWidget(enhance); buttonRow->addWidget(stop);
        layout->addLayout(buttonRow); enhance->setEnabled(false); stop->setEnabled(false);
        auto *comparisonRow = new QHBoxLayout;
        originalButton = new QPushButton("Hold for original", this);
        auto *saveButton = new QPushButton("Save preview...", this);
        comparisonRow->addWidget(originalButton); comparisonRow->addWidget(saveButton); layout->addLayout(comparisonRow);
        connect(originalButton, &QPushButton::pressed, this, [this] {
            comparingOriginal = true; if (overlay) overlay->hide(); if (!originalFrame.isNull()) preview->setImage(originalFrame);
        });
        connect(originalButton, &QPushButton::released, this, [this] {
            comparingOriginal = false; if (!result.isNull()) showResult(result);
        });
        connect(saveButton, &QPushButton::clicked, this, [this] {
            if (result.isNull()) { status->setText("Start a preview before saving."); return; }
            QString path = QFileDialog::getSaveFileName(this, "Save enhanced preview", "Iray-enhanced-preview.png", "PNG image (*.png)");
            if (!path.isEmpty() && !savePreview(path)) status->setText("Could not save preview.");
        });
        status = new QLabel("Preview stopped", this); status->setWordWrap(true); layout->addWidget(status);
        preview = new PreviewCanvas(this); layout->addWidget(preview, 1);
        renderTools = new RenderTools(tabs, python, project, runtime, [this] {
            return QJsonObject{{"style", appearance->currentData().toInt()}, {"tone", tone->value()},
                {"structure", structure->value()}, {"skin", skin->value()}, {"auto_mask", autoMask->isChecked()}, {"blend", blend->value()}};
        }, [this] { stopWorker(); });
        tabs->addTab(renderTools, "Render output");
        process = new QProcess(this); timer = new QTimer(this); watchdog = new QTimer(this);
#ifdef Q_OS_WIN
        process->setCreateProcessArgumentsModifier([](QProcess::CreateProcessArguments *args) {
            args->flags |= CREATE_NO_WINDOW;
        });
#endif
        debounce = new QTimer(this); debounce->setSingleShot(true); debounce->setInterval(200);
        connect(debounce, &QTimer::timeout, this, &PuenteIrayPreviewPane::capture);
        timer->setInterval(1000); watchdog->setInterval(250);
        connect(start, &QPushButton::clicked, this, &PuenteIrayPreviewPane::startWorker);
        connect(stop, &QPushButton::clicked, this, &PuenteIrayPreviewPane::stopWorker);
        connect(enhance, &QPushButton::clicked, this, &PuenteIrayPreviewPane::capture);
        connect(timer, &QTimer::timeout, this, &PuenteIrayPreviewPane::capture);
        connect(watchdog, &QTimer::timeout, this, [this] {
            if (busy && operation.elapsed() > 45000) {
                stopWorker(); status->setText("GPU worker timed out and was stopped.");
            }
        });
        connect(process, &QProcess::readyReadStandardOutput, this, &PuenteIrayPreviewPane::readWorker);
        connect(process, &QProcess::readyReadStandardError, this, [this] {
            QByteArray error = process->readAllStandardError();
            if (!error.isEmpty()) status->setText(QString::fromUtf8(error.right(2048)));
        });
        connect(process, &QProcess::finished, this, [this](int code, QProcess::ExitStatus) {
            stopped(); cleanupSession(); status->setText(QString("Worker exited (%1)").arg(code));
        });
        connect(process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
            if (error == QProcess::FailedToStart) {
                stopped(); cleanupSession(); status->setText(process->errorString());
            }
        });
        connect(live, &QCheckBox::toggled, this, [this](bool checked) {
            if (ready && checked) timer->start(); else timer->stop();
        });
        connect(autoMask, &QCheckBox::toggled, this, &PuenteIrayPreviewPane::requestUpdate);
        connect(appearance, &QComboBox::currentIndexChanged, this, &PuenteIrayPreviewPane::requestUpdate);
        connect(overlayOn, &QCheckBox::toggled, this, [this](bool checked) {
            if (overlay && !checked) overlay->hide();
            if (checked && !result.isNull()) showResult(result);
        });
        connect(detail, &QPushButton::clicked, this, [this] {
            tone->setValue(0); structure->setValue(1); skin->setValue(-1); autoMask->setChecked(false);
        });
        connect(stronger, &QPushButton::clicked, this, [this] {
            tone->setValue(1); structure->setValue(1.5); skin->setValue(1.5); autoMask->setChecked(true);
        });
        connect(dzScene, SIGNAL(drawnDataChanged()), this, SLOT(invalidate()));
        if (dzApp->getInterface()) {
            connect(dzApp->getInterface()->getViewportMgr(), &DzViewportMgr::activeViewSwitched, this, [this] {
                if (viewport) attachViewport(activeViewport());
            });
        }
    }
    ~PuenteIrayPreviewPane() override {
        stopWorker(); if (viewport) viewport->removeEventFilter(this); delete overlay.data();
    }
    Q_INVOKABLE bool configureWorker(const QString &executable, const QString &folder, const QString &nr) {
        if (process->state() != QProcess::NotRunning) return false;
        python->setText(executable); project->setText(folder); runtime->setText(nr); setupGroup->hide(); return true;
    }
    Q_INVOKABLE void beginPreview() { startWorker(); }
    Q_INVOKABLE bool importNrRuntime(const QString &source) {
        if (process->state() != QProcess::NotRunning || renderTools->state()["busy"].toBool()) {
            status->setText("Detén el procesamiento antes de cambiar el runtime."); return false;
        }
        QString error; QString folder = PuenteWorker::importRuntime(project->text(), source, error);
        if (folder.isEmpty()) { status->setText(error); return false; }
        runtime->setText(folder);
        QSettings local("Puente Labs", "Iray Neural Preview"); local.setValue("runtime", folder);
        status->setText("Runtime copiado sin modificaciones. La compatibilidad se comprueba al iniciar el procesamiento.");
        return true;
    }
    Q_INVOKABLE QVariantMap localSetupState() const {
        return {{"packageRoot", project->text()}, {"runtime", runtime->text()},
                {"worker", PuenteWorker::executable(project->text())}, {"packaged", PuenteWorker::isPackaged(project->text())}};
    }
    Q_INVOKABLE void endPreview() { stopWorker(); }
    Q_INVOKABLE void enhanceNow() { capture(); }
    Q_INVOKABLE void setLiveRefresh(bool enabled) { live->setChecked(enabled); }
    Q_INVOKABLE void setViewportOverlay(bool enabled) { overlayOn->setChecked(enabled); }
    Q_INVOKABLE bool setAppearance(int style) {
        int index = appearance->findData(style); if (index < 0) return false;
        appearance->setCurrentIndex(index); return true;
    }
    Q_INVOKABLE bool setPreviewSettings(double newTone, double newStructure, double newSkin, bool mask, double strength) {
        if (!qIsFinite(newTone) || !qIsFinite(newStructure) || !qIsFinite(newSkin) || !qIsFinite(strength)
            || newTone < 0 || newTone > 2 || newStructure < 0 || newStructure > 2
            || newSkin < -1 || newSkin > 2 || strength < 0 || strength > 1) return false;
        tone->setValue(newTone); structure->setValue(newStructure); skin->setValue(newSkin);
        autoMask->setChecked(mask); blend->setValue(strength); return true;
    }
    Q_INVOKABLE QVariantMap previewState() const {
        QVariantMap state;
        state["ready"] = ready; state["busy"] = busy; state["frames"] = completedFrames;
        state["status"] = status->text(); state["hasImage"] = !result.isNull();
        state["workerPid"] = process->processId(); state["visible"] = isVisible();
        state["width"] = result.width(); state["height"] = result.height();
        state["comparingOriginal"] = comparingOriginal; state["blend"] = blend->value();
        state["appearance"] = appearance->currentData().toInt(); state["live"] = live->isChecked();
        state["overlayVisible"] = overlay && overlay->isVisible(); return state;
    }
    Q_INVOKABLE bool savePreview(const QString &path) const { return !result.isNull() && result.save(path, "PNG"); }
    Q_INVOKABLE bool savePaneSnapshot(const QString &path) { return grab().save(path, "PNG"); }
    Q_INVOKABLE bool configureRender(int factor, const QString &method, bool enhance, double strength, bool smaller) {
        return renderTools->configure(factor, method, enhance, strength, smaller);
    }
    Q_INVOKABLE bool processRenderFile(const QString &path, const QString &newDirectory) { return renderTools->processFile(path, newDirectory); }
    Q_INVOKABLE bool renderAndProcess(const QString &newDirectory) { return renderTools->renderTo(newDirectory); }
    Q_INVOKABLE QVariantMap renderState() const { return renderTools->state(); }
    Q_INVOKABLE void setAutomaticRenderProcessing(bool enabled) { renderTools->setAutomatic(enabled); }
    Q_INVOKABLE void cancelRenderProcessing() { renderTools->cancelProcessing(); }
    Q_INVOKABLE bool configureRenderPython(const QString &path) { return renderTools->configurePython(path); }
    Q_INVOKABLE void showRenderTools() { tabs->setCurrentWidget(renderTools); }
#ifdef PUENTE_ENABLE_VALIDATION_API
    Q_INVOKABLE void validationCrashWorker() { process->kill(); }
    Q_INVOKABLE void validationHoldOriginal(bool pressed) {
        QMetaObject::invokeMethod(originalButton, pressed ? "pressed" : "released", Qt::DirectConnection);
    }
    Q_INVOKABLE bool validationViewportSnapshot(const QString &path) {
        return viewport && viewport->grab().save(path, "PNG");
    }
    Q_INVOKABLE QVariantMap validationWait(int minimumFrames, int timeoutMs) {
        QEventLoop loop; QTimer poll; QTimer deadline;
        connect(&poll, &QTimer::timeout, &loop, [this, minimumFrames, &loop] {
            if (ready && !busy && completedFrames >= minimumFrames) loop.quit();
        });
        connect(&deadline, &QTimer::timeout, &loop, &QEventLoop::quit);
        deadline.setSingleShot(true); deadline.start(qBound(1, timeoutMs, 45000)); poll.start(20);
        loop.exec(); return previewState();
    }
#endif
protected:
    bool eventFilter(QObject *object, QEvent *event) override {
        if (object == viewport && (event->type() == QEvent::MouseButtonPress || event->type() == QEvent::Wheel
            || event->type() == QEvent::KeyPress || event->type() == QEvent::Resize
            || (event->type() == QEvent::MouseMove && static_cast<QMouseEvent *>(event)->buttons() != Qt::NoButton))) invalidate();
        return DzPane::eventFilter(object, event);
    }
    void hideEvent(QHideEvent *event) override { stopWorker(); DzPane::hideEvent(event); }
private slots:
    void bindCamera() {
        DzCamera *camera = viewport ? viewport->getCamera() : nullptr;
        if (trackedCamera == camera) return;
        invalidate();
        if (trackedCamera) disconnect(trackedCamera, nullptr, this, nullptr);
        trackedCamera = camera;
        if (camera) {
            connect(camera, SIGNAL(transformChanged()), this, SLOT(invalidate()));
            connect(camera, SIGNAL(projectionChanged()), this, SLOT(invalidate()));
        }
    }
    void invalidate() {
        ++generation; result = originalFrame = QImage(); if (overlay) overlay->hide(); if (preview) preview->setImage(QImage());
    }
private:
    void requestUpdate() {
        invalidate(); captureQueued = true; if (ready) debounce->start();
    }
    QDoubleSpinBox *slider(QFormLayout *form, const QString &label, int low, int high, int initial) {
        auto *row = new QWidget(this); auto *layout = new QHBoxLayout(row);
        layout->setContentsMargins(0, 0, 0, 0);
        auto *control = new QSlider(Qt::Horizontal, row); control->setRange(low, high); control->setValue(initial);
        auto *spin = new QDoubleSpinBox(row); spin->setRange(low / 100.0, high / 100.0);
        spin->setDecimals(2); spin->setSingleStep(0.05); spin->setValue(initial / 100.0);
        layout->addWidget(control, 1); layout->addWidget(spin); form->addRow(label, row);
        connect(control, &QSlider::valueChanged, this, [this, spin](int value) {
            spin->blockSignals(true); spin->setValue(value / 100.0); spin->blockSignals(false); requestUpdate();
        });
        connect(spin, &QDoubleSpinBox::valueChanged, this, [this, control](double value) {
            control->blockSignals(true); control->setValue(qRound(value * 100)); control->blockSignals(false); requestUpdate();
        });
        return spin;
    }
    void startWorker() {
        if (process->state() != QProcess::NotRunning) return;
        QString root = QDir(project->text()).absolutePath(), nr = QDir(runtime->text()).absolutePath();
        if (PuenteWorker::isPackaged(root)) {
            QString error = PuenteWorker::check(root, nr, true, false, 1);
            if (!error.isEmpty()) { status->setText(error); return; }
        } else if (!QFileInfo(python->text()).isFile() || !QFileInfo(root + "/viewport_worker.py").isFile()
            || !QFileInfo(nr + "/nvngx_dlssnr.dll").isFile()
            || !QFileInfo(nr + "/caller/nvngx.dll_comfy.dll").isFile()) {
            status->setText("Set an existing Python executable, prototype folder, and staged runtime folder."); return;
        }
        session = QDir::tempPath() + "/PuenteIrayPreview-" + QUuid::createUuid().toString(QUuid::WithoutBraces);
        if (!QDir().mkdir(session)) { status->setText("Could not create private preview cache"); return; }
        QSettings settings("Puente Labs", "Iray Neural Preview");
        settings.setValue("python", python->text()); settings.setValue("project", root); settings.setValue("runtime", nr);
        QStringList args = PuenteWorker::arguments(root, "viewport", {"--session", session,
            "--runtime", nr, "--parent-pid", QString::number(QCoreApplication::applicationPid()), "--transport", "rgba"});
        ready = false; busy = true; operation.start(); watchdog->start();
        start->setEnabled(false); stop->setEnabled(true); setConfigEnabled(false);
        status->setText("Initializing GPU worker..."); process->setWorkingDirectory(root);
        process->start(PuenteWorker::isPackaged(root) ? PuenteWorker::executable(root) : python->text(), args);
    }
    void stopWorker() {
        stopped();
        if (process->state() != QProcess::NotRunning) {
            process->kill(); // Only this pane's worker. No vendor shutdown inside Daz.
            process->waitForFinished(1500);
        }
        if (process->state() == QProcess::NotRunning) cleanupSession();
        status->setText("Preview stopped");
    }
    void stopped() {
        timer->stop(); watchdog->stop(); debounce->stop(); ready = busy = captureQueued = false; invalidate();
        start->setEnabled(true); stop->setEnabled(false); enhance->setEnabled(false); setConfigEnabled(true);
    }
    void setConfigEnabled(bool enabled) {
        python->setReadOnly(!enabled); project->setReadOnly(!enabled); runtime->setReadOnly(!enabled);
    }
    void cleanupSession() {
        if (session.isEmpty()) return;
        // Fixed owned filenames only; no recursive deletion or runtime deletion.
        for (const char *name : {"frame.png", "enhanced.png", "enhanced.tmp.png", "frame.rgb", "enhanced.rgb", "enhanced.tmp.rgb",
            "frame.rgba", "enhanced.rgba", "enhanced.tmp.rgba", "coverage.alpha", "latest-report.json"})
            QFile::remove(session + "/" + name);
        QDir().rmdir(session); session.clear();
    }
    Dz3DViewport *activeViewport() const {
        DzMainWindow *window = dzApp->getInterface();
        DzViewport *active = window ? window->getViewportMgr()->getActiveViewport() : nullptr;
        return active ? active->get3DViewport() : nullptr;
    }
    void attachViewport(Dz3DViewport *target) {
        if (viewport == target) return;
        invalidate(); if (viewport) { viewport->removeEventFilter(this); disconnect(viewport, nullptr, this, nullptr); }
        delete overlay.data(); viewport = target;
        if (target) {
            target->installEventFilter(this);
            connect(target, SIGNAL(viewChanged()), this, SLOT(bindCamera()));
            connect(target, SIGNAL(drawStyleChanged(DzDrawStyle*)), this, SLOT(invalidate()));
            overlay = new PreviewOverlay(target);
        }
        bindCamera();
    }
    void capture() {
        if (!ready || busy || !isVisible() || QApplication::mouseButtons() != Qt::NoButton) return;
        attachViewport(activeViewport()); if (!viewport) { status->setText("No active 3D viewport"); return; }
        if (viewport->isNavigating()) { invalidate(); return; }
        if (!viewport->getUserDrawStyle().contains("Iray", Qt::CaseInsensitive)) {
            invalidate(); status->setText("Select NVIDIA Iray in the active viewport"); return;
        }
        debounce->stop(); operation.restart();
        // Studio 6 live validation confirmed this captures Iray and excludes
        // our child overlay. Manage declared color spaces before RGB8 transfer.
        QImage frame = viewport->captureImage().getValue();
        if (frame.colorSpace().isValid()) frame.convertToColorSpace(QColorSpace::SRgb);
        else frame.setColorSpace(QColorSpace::SRgb);
        frame = frame.convertToFormat(QImage::Format_RGBA8888);
        if (frame.isNull() || frame.width() > 4096 || frame.height() > 4096) {
            invalidate(); status->setText("Viewport capture failed or exceeds 4096 pixels per side"); return;
        }
        QByteArray packed; packed.resize(frame.width() * frame.height() * 4);
        for (int row = 0; row < frame.height(); ++row)
            std::memcpy(packed.data() + row * frame.width() * 4, frame.constScanLine(row), frame.width() * 4);
        pendingCoverage.resize(frame.width() * frame.height());
        for (int pixel = 0; pixel < pendingCoverage.size(); ++pixel) {
            int alpha = static_cast<uchar>(packed[pixel * 4 + 3]);
            pendingCoverage[pixel] = static_cast<char>(qBound(0, qRound((alpha / 255.0 - 0.90) * 2550.0), 255));
        }
        // Preserve the viewport's top controls and camera/navigation HUD. The
        // mask is in physical capture pixels, including high-DPI viewports.
        double sx = double(frame.width()) / qMax(1, viewport->width());
        double sy = double(frame.height()) / qMax(1, viewport->height());
        auto protect = [&](QRect area) {
            area = area.intersected(QRect(0, 0, frame.width(), frame.height()));
            for (int row = area.top(); row <= area.bottom(); ++row)
                if (area.width() > 0) std::memset(pendingCoverage.data() + row * frame.width() + area.left(), 0, area.width());
        };
        protect(QRect(0, 0, frame.width(), qRound(30 * sy)));
        protect(QRect(frame.width() - qRound(210 * sx), 0, qRound(210 * sx), qRound(220 * sy)));
        QFile mask(session + "/coverage.alpha");
        if (!mask.open(QIODevice::WriteOnly) || mask.write(pendingCoverage) != pendingCoverage.size()) {
            invalidate(); status->setText("Cannot transfer preview mask"); return;
        }
        mask.close();
        QFile input(session + "/frame.rgba");
        if (!input.open(QIODevice::WriteOnly) || input.write(packed) != packed.size()) {
            invalidate(); status->setText("Cannot transfer preview frame"); return;
        }
        input.close(); pendingOriginalFrame = frame;
        pendingSize = frame.size(); pendingId = ++sequence; pendingGeneration = generation;
        QStringList fields;
        fields << QString::number(pendingId) << QString::number(appearance->currentData().toInt()) << "3"
            << QString::number(tone->value()) << QString::number(structure->value()) << QString::number(skin->value())
            << QString::number(autoMask->isChecked() ? 1 : 0) << QString::number(blend->value())
            << QString::number(frame.width()) << QString::number(frame.height());
        QString request = fields.join('\t') + '\n';
        busy = true; captureQueued = false;
        process->write(request.toLatin1()); status->setText("Enhancing Iray preview...");
    }
    void readWorker() {
        while (process->canReadLine()) {
            QList<QByteArray> parts = process->readLine().trimmed().split('\t');
            if (parts.size() == 2 && parts[0] == "READY") {
                ready = true; busy = false; enhance->setEnabled(true);
                status->setText("Ready: " + QString::fromUtf8(QByteArray::fromBase64(parts[1])));
                if (live->isChecked()) timer->start();
                captureQueued = true; debounce->start(100);
            } else if (parts.size() == 5 && parts[0] == "OK" && parts[1].toInt() == pendingId) {
                busy = false;
                if (pendingGeneration != generation || !viewport || activeViewport() != viewport) {
                    status->setText("View changed; waiting for a new preview");
                    if (captureQueued) debounce->start(1);
                    continue;
                }
                QFile output(session + "/enhanced.rgba");
                if (!output.open(QIODevice::ReadOnly)) { invalidate(); status->setText("Could not read enhanced frame"); continue; }
                QByteArray pixels = output.readAll();
                if (pixels.size() != pendingSize.width() * pendingSize.height() * 4) {
                    invalidate(); status->setText("Invalid output dimensions"); continue;
                }
                QImage image(reinterpret_cast<const uchar *>(pixels.constData()), pendingSize.width(), pendingSize.height(),
                    pendingSize.width() * 4, QImage::Format_RGBA8888);
                image = image.copy(); image.setColorSpace(QColorSpace::SRgb);
                ++completedFrames;
                originalFrame = pendingOriginalFrame; resultCoverage = pendingCoverage;
                showResult(image); status->setText(QString("Updated in %1 ms (GPU %2 ms)").arg(operation.elapsed()).arg(QString::fromLatin1(parts[2])));
                if (captureQueued) debounce->start(1);
            } else if (parts.size() == 3 && parts[0] == "ERROR") {
                busy = false; invalidate(); status->setText(QString::fromUtf8(QByteArray::fromBase64(parts[2])));
                if (captureQueued) debounce->start(1);
            }
        }
    }
    void showResult(const QImage &image) {
        result = image;
        preview->setImage(comparingOriginal ? originalFrame : image);
        if (overlay && viewport && overlayOn->isChecked() && !comparingOriginal && blend->value() > 0) {
            QImage layer = image.convertToFormat(QImage::Format_RGBA8888).copy();
            for (int row = 0; row < layer.height(); ++row) {
                uchar *pixels = layer.scanLine(row);
                for (int col = 0; col < layer.width(); ++col)
                    pixels[col * 4 + 3] = static_cast<uchar>(resultCoverage[row * layer.width() + col]);
            }
            overlay->image = layer; overlay->setGeometry(viewport->rect()); overlay->show(); overlay->raise(); overlay->update();
        } else if (overlay) {
            overlay->hide();
        }
    }
    QLineEdit *python = nullptr, *project = nullptr, *runtime = nullptr;
    QTabWidget *tabs;
    RenderTools *renderTools;
    QDoubleSpinBox *tone, *structure, *skin, *blend;
    QComboBox *appearance;
    QCheckBox *autoMask, *live, *overlayOn;
    QLabel *status;
    PreviewCanvas *preview = nullptr;
    QGroupBox *setupGroup;
    QPushButton *start, *stop, *enhance, *originalButton;
    QProcess *process; QTimer *timer, *watchdog, *debounce; QElapsedTimer operation;
    QPointer<Dz3DViewport> viewport; QPointer<PreviewOverlay> overlay;
    QPointer<DzCamera> trackedCamera;
    QString session; QImage result, originalFrame, pendingOriginalFrame; QSize pendingSize;
    QByteArray pendingCoverage, resultCoverage;
    bool ready = false, busy = false, captureQueued = false, comparingOriginal = false;
    int sequence = 0, generation = 0, pendingGeneration = 0, pendingId = 0;
    int completedFrames = 0;
};

class PuenteIrayPreviewPaneAction : public DzPaneAction {
    Q_OBJECT
public:
    PuenteIrayPreviewPaneAction() : DzPaneAction("PuenteIrayPreviewPane") {}
};

DZ_PLUGIN_DEFINITION("Puente Labs Iray Neural Preview");
DZ_PLUGIN_AUTHOR("Puente Labs");
DZ_PLUGIN_VERSION(0, 3, 0, 0);
DZ_PLUGIN_DESCRIPTION("Experimental Iray viewport and still-render enhancement with optional 2x/4x upscaling.");
DZ_PLUGIN_CLASS_GUID(PuenteIrayPreviewPane, 865c91d6-c0e3-4d0a-8158-9f1badfdd902);
DZ_PLUGIN_CLASS_GUID(PuenteIrayPreviewPaneAction, 3470152b-756e-48a6-ae83-203e3fda4c54);
#include "PreviewPane.moc"
