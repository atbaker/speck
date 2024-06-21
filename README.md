# speck-app

## PyInstaller

pyinstaller speck.spec

## Windows

Have to `pip install pywin32` outside of Pipenv because of this bug: https://github.com/mhammond/pywin32/issues/1177

Also need to rename `llamafile` to `llamafile.exe`, and update its filename in `speck.spec`
