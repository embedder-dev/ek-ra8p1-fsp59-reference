"""EASE via embedder e2 exec: PROJECT NODE=OPTION ... [--apply]."""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
from org.eclipse.core.resources import ResourcesPlugin

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("project")
parser.add_argument("settings", nargs="+")
parser.add_argument("--apply", action="store_true")
args = parser.parse_args(list(argv[1:]))
configuration = openDDSCConfiguration(args.project)
changes = []
seen = set()
for setting in args.settings:
    key, separator, value = setting.partition("=")
    if not separator or not key.startswith("board.clock.") or key in seen:
        raise ValueError("Expected a unique board.clock.NODE=OPTION: " + setting)
    seen.add(key)
    node = configuration.getClockNode(key)
    options = [str(option) for option in jlist(node.getOptions())]
    if value not in options:
        raise ValueError("Invalid option for " + key + ": " + value + "; choices: " + ", ".join(options))
    changes.append((node, str(node.getValue()), value))
if args.apply:
    try:
        for node, old, value in changes:
            node.setValue(value)
            if str(node.getValue()) != value:
                raise RuntimeError("Clock option was not accepted: " + str(node.getId()))
    except Exception:
        for node, old, value in reversed(changes):
            if str(node.getValue()) != old:
                node.setValue(old)
        raise
    configuration.save()
    generateProjectContent(args.project, None)
project = ResourcesPlugin.getWorkspace().getRoot().getProject(args.project)
path = Path(str(project.getLocation().toOSString())) / "configuration.xml"
serialized = {node.get("id"): node.get("option") for node in
              ET.parse(str(path)).findall("./raClockConfiguration/node")}
if args.apply:
    for node, old, value in changes:
        if serialized.get(str(node.getId())) != value:
            raise RuntimeError("Saved clock option mismatch: " + str(node.getId()))
result = {"project": args.project, "applied": args.apply,
          "changes": [{"id": str(node.getId()), "before": old, "requested": value,
                       "saved": serialized.get(str(node.getId()))} for node, old, value in changes]}
