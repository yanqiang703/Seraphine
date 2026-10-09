'''
PyQt-Fluent-Widgets without Ads.
'''

import sys
import io
from contextlib import redirect_stdout

# Suppress ads by redirecting stdout to a null buffer during import
_null_out = io.StringIO()
with redirect_stdout(_null_out):
    from qfluentwidgets import *
    from qfluentwidgets.components.widgets.line_edit import CompleterMenu, LineEditButton
    from qfluentwidgets.common.animation import BackgroundAnimationWidget
    from qfluentwidgets.common.animation import BackgroundColorObject
    from qfluentwidgets.window.fluent_window import FluentWindowBase
    from qfluentwidgets.window.stacked_widget import StackedWidget
    from qfluentwidgets.components.widgets.frameless_window import FramelessWindow
    from qframelesswindow import SvgTitleBarButton