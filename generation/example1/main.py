import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import register_forward

@register_forward("example1")
def forward():
    print("example1")