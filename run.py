import os
import pathlib

import uvicorn

if __name__ == "__main__":
    os.chdir(pathlib.Path(__file__).parent)
    uvicorn.run("miniclaw:app", host="0.0.0.0", port=11223)
