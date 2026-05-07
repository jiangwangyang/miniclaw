import os
import pathlib

import uvicorn

if __name__ == "__main__":
    os.chdir(pathlib.Path(__file__).parent)
    uvicorn.run("miniclaw:app", host="localhost", port=11223)
