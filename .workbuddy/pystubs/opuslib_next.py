"""仅用于本地跑单测的 opuslib_next 占位模块（Windows 缺 libopus 原生库）。

通过 PYTHONPATH 前置本目录，使其优先于 site-packages 里的真包被导入。
不参与任何部署。
"""


class _Any:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return _Any()

    def __call__(self, *a, **k):
        return _Any()


def __getattr__(name):
    return _Any
