[app]
title = MiNERVA Deck
project_dir = ..
input_file = minerva_deck.py
exec_directory = dist
project_file =
icon = packaging/assets/minerva-deck.ico

[python]
python_path =
packages = nuitka==4.1.3,ordered-set==4.1.0,zstandard==0.23.0

[qt]
qml_files =
excluded_qml_plugins =
modules = Core,Gui,Widgets,Network,WebEngineCore,WebEngineWidgets,Svg
plugins =

[nuitka]
mode = onefile
extra_args = --quiet --enable-plugin=pyside6 --windows-console-mode=disable --windows-product-name="MiNERVA Deck" --windows-file-description="MiNERVA Deck desktop application" --windows-company-name=MiNERVA --windows-file-version=1.0.0.0 --windows-product-version=1.0.0.0 --include-data-dir=public=public --include-data-dir=packaging=packaging --include-data-dir=build/native=native --include-data-dir=build/licenses=licenses
