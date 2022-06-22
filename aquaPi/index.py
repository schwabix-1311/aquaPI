#!/usr/bin/env python3

from flask import (
    Blueprint, render_template
)


bp = Blueprint('index', __name__)


@bp.route('/')
def index():
    return render_template('index.html')
