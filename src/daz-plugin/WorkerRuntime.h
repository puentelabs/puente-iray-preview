#pragma once
#include <QtCore/QString>
#include <QtCore/QStringList>

namespace PuenteWorker {
QString packagedRoot();
bool isPackaged(const QString &root);
QString executable(const QString &root);
QStringList arguments(const QString &root, const QString &operation, const QStringList &options);
QString check(const QString &root, const QString &runtime, bool nr, bool upscale, int scale);
QString importRuntime(const QString &root, const QString &source, QString &error);
}
