from PyInstaller.utils.hooks import collect_data_files

# Gather template files
datas = collect_data_files(
    'emails',
    includes=['templates']
)
