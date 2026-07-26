[app]
title = MiNERVA Deck
project_dir = ..
input_file = minerva_deck.py
exec_directory = build/deck
project_file =
icon = packaging/assets/minerva-deck.png

[python]
python_path =
packages = nuitka==4.1.3,ordered-set==4.1.0,zstandard==0.25.0

[qt]
qml_files =
excluded_qml_plugins =
modules = Core,Gui,Widgets,Network,WebEngineCore,WebEngineWidgets,Svg
plugins =

[nuitka]
mode = standalone
extra_args = --quiet --enable-plugin=pyside6 --include-data-dir=public=public --include-data-dir=packaging=packaging --include-data-dir=build/native=native --include-data-dir=build/licenses=licenses
