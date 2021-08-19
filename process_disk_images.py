# Process legacy disk images (extract contents and run various reports on image and files)

import argparse
import datetime
import os
import shutil
import subprocess
import time

import Objects