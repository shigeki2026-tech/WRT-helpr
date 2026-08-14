# -*- coding: utf-8 -*-
"""他OP向けの閲覧専用・簡易エントリーポイント。"""

import os


os.environ["WRT_SIMPLE_OP_MODE"] = "1"

from app import main  # noqa: E402


if __name__ == "__main__":
    main()
