from PyQt5.QtCore import QThread, QObject

def _launch_worker(worker: QObject, *finish_signals) -> QThread:
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    for sig in finish_signals:
        sig.connect(thread.quit)
    thread.start()
    return thread