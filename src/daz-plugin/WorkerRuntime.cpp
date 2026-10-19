#include "WorkerRuntime.h"
#include <QtCore/QDir>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QProcess>
#include <QtCore/QFile>
#include <QtCore/QCryptographicHash>
#include <QtCore/QStandardPaths>
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <Windows.h>

namespace PuenteWorker {
QString packagedRoot() {
    HMODULE module = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&packagedRoot), &module)) return {};
    wchar_t path[32768];
    DWORD count = GetModuleFileNameW(module, path, 32768);
    if (!count || count >= 32768) return {};
    QString root = QFileInfo(QString::fromWCharArray(path, count)).absolutePath() + "/PuenteIrayPreview";
    return isPackaged(root) ? root : QString();
}
bool isPackaged(const QString &root) {
#ifdef PUENTE_PACKAGED_ONLY
    // Un paquete incompleto debe dar error, nunca recurrir a un Python ajeno.
    Q_UNUSED(root);
    return true;
#else
    return QFileInfo(executable(root)).isFile();
#endif
}
QString executable(const QString &root) { return QDir(root).filePath("puente-worker.exe"); }
QString importRuntime(const QString &root, const QString &source, QString &error) {
    if (QFileInfo(source).fileName().compare("nvngx_dlssnr.dll", Qt::CaseInsensitive) != 0) {
        error = "Selecciona el archivo nvngx_dlssnr.dll compatible que tienes derecho a utilizar."; return {};
    }
    auto digest = [](const QString &path) {
        QFile file(path); QCryptographicHash hash(QCryptographicHash::Sha256);
        if (!file.open(QIODevice::ReadOnly) || !hash.addData(&file)) return QByteArray();
        return hash.result().toHex();
    };
    QByteArray hash = digest(source);
    QString helper = QDir(root).filePath("backend/nvngx.dll_comfy.dll");
    QByteArray helperHash = digest(helper);
    if (hash.isEmpty() || helperHash.isEmpty()) { error = "No se pudo leer el DLL seleccionado o falta el helper del paquete."; return {}; }
    // El runtime experimental falla si la ruta efectiva del caller supera
    // MAX_PATH. En aplicaciones empaquetadas Windows puede alargar AppData.
    // Un identificador compacto evita dos niveles de SHA-256 completos;
    // copyExact sigue verificando ambos hashes completos antes de reutilizarlo.
    QByteArray identifier = QCryptographicHash::hash(hash + helperHash, QCryptographicHash::Sha256).toHex().left(24);
    QString destination = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation)
        + "/PuenteLabs/IrayPreview/runtimes/" + QString::fromLatin1(identifier);
    if (!QDir().mkpath(destination + "/caller")) { error = "No se pudo crear la carpeta de runtime del usuario."; return {}; }
    const QString target = destination + "/nvngx_dlssnr.dll", caller = destination + "/caller/nvngx.dll_comfy.dll";
    auto copyExact = [&digest](const QString &from, const QString &to, const QByteArray &expected) {
        if (!QFileInfo::exists(to) && !QFile::copy(from, to)) return false;
        return digest(to) == expected;
    };
    if (!copyExact(source, target, hash) || !copyExact(helper, caller, helperHash)) {
        error = "No se pudo preparar una copia idéntica del runtime. Se conservaron los archivos existentes."; return {};
    }
    if (QFileInfo(caller).canonicalFilePath().size() >= MAX_PATH) {
        error = "La ruta del runtime supera el límite de este backend. Prepara una carpeta más corta y selecciónala en configuración."; return {};
    }
    return destination;
}
QStringList arguments(const QString &root, const QString &operation, const QStringList &options) {
    QStringList result;
    if (isPackaged(root)) result << operation;
    else result << "-B" << QDir(root).filePath(operation + "_worker.py");
    return result + options;
}
QString check(const QString &root, const QString &runtime, bool nr, bool upscale, int scale) {
    QStringList args{"check", "--scale", QString::number(scale)};
    if (nr) args << "--nr" << "--runtime" << runtime;
    if (upscale) args << "--upscale";
    QProcess probe;
    probe.setCreateProcessArgumentsModifier([](QProcess::CreateProcessArguments *args) { args->flags |= CREATE_NO_WINDOW; });
    probe.start(executable(root), args);
    if (!probe.waitForFinished(30000)) {
        probe.kill(); probe.waitForFinished(1500);
        return "El diagnóstico del runtime no terminó en 30 segundos. No se inició el render.";
    }
    QJsonObject report = QJsonDocument::fromJson(probe.readAllStandardOutput()).object();
    if (probe.exitStatus() == QProcess::NormalExit && probe.exitCode() == 0 && report["status"].toString() == "passed") return {};
    QString error = report["error"].toString();
    if (error.isEmpty()) error = QString::fromUtf8(probe.readAllStandardError()).right(2048);
    return error.isEmpty() ? "No se pudo comprobar el runtime incluido. Reinstala el paquete completo." : error;
}
}
