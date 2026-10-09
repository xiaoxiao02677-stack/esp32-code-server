"""仅用于本地跑单测的 pydub 占位模块（Python 3.13 移除了 audioop，pydub 无法导入）。

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
