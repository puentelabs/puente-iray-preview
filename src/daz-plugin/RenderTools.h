// Puente Labs, MIT. Still-render integration; renderer and masters stay separate.
#pragma once
#include <QtWidgets/QWidget>
#include <QtCore/QJsonObject>
#include <QtCore/QPointer>
#include <functional>
class QLineEdit;
class QComboBox;
class QCheckBox;
class QDoubleSpinBox;
class QPushButton;
class QLabel;
class QProcess;
class QTimer;
class RenderTools : public QWidget {
    Q_OBJECT
public:
    RenderTools(QWidget *parent, QLineEdit *python, QLineEdit *project, QLineEdit *runtime,
                std::function<QJsonObject()> controls, std::function<void()> stopPreview);
    ~RenderTools() override;
    bool processFile(const QString &input, const QString &outputDirectory);
    bool renderTo(const QString &outputDirectory);
    bool configure(int scale, const QString &method, bool enhance, double strength, bool reduced);
    bool configurePython(const QString &executable);
    void setAutomatic(bool enabled);
    void cancelProcessing() { cancel(); }
    QVariantMap state() const;
private:
    void cancel();
    void updateEnabled();
    void renderStarted();
    void renderFinished(bool succeeded);
    QJsonObject jobFor(const QString &input, const QString &outputDirectory) const;
    bool launch(const QJsonObject &job);
    QString dependencyError(const QJsonObject &job) const;
    QString newOutputFolder(const QString &parent) const;
    QLineEdit *python, *project, *runtime, *gpuPython;
    QComboBox *scale, *method;
    QDoubleSpinBox *strength;
    QCheckBox *enhance, *reduced, *automatic;
    QPushButton *renderButton, *fileButton, *cancelButton, *openButton;
    QLabel *status;
    QProcess *worker;
    QTimer *deadline;
    std::function<QJsonObject()> controls;
    std::function<void()> stopPreview;
    bool ownRender = false, rendering = false;
    QString outputFolder, automaticSource;
    QJsonObject automaticJob;
    qint64 automaticStart = 0;
    int completed = 0;
};
