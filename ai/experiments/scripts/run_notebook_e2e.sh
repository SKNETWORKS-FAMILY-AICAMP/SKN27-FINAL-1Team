#!/bin/sh
set -e
jupyter nbconvert \
  --to notebook \
  --execute LightFM_Model.ipynb \
  --output /tmp/LightFM_Model.executed.ipynb \
  --ExecutePreprocessor.timeout=600
echo "notebook e2e ok"
