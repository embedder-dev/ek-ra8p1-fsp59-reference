"""EASE via embedder e2 exec: PROJECT MODULE PROPERTY=OPTION ... [--apply].

Without --apply, validate and report only. MODULE is the full MDF module id;
its unique HAL stack must already exist. Applying saves and regenerates, but
never builds or changes packs.
"""
import argparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("project")
parser.add_argument("module")
parser.add_argument("settings", nargs="+")
parser.add_argument("--apply", action="store_true")
args = parser.parse_args(list(argv[1:]))

configuration = openDDSCConfiguration(args.project)
stacks = [stack for thread in jlist(configuration.getThreads()) if thread.isHal()
          for stack in jlist(thread.getStacks())
          if str(stack.getId()).rsplit(".", 1)[0] == args.module]
if len(stacks) != 1:
    raise ValueError("Expected one HAL stack for " + args.module + "; found " + str(len(stacks)))
stack = stacks[0]

changes = []
seen = set()
for setting in args.settings:
    key, separator, value = setting.partition("=")
    if not separator or not key.startswith("config.") or not value or key in seen:
        raise ValueError("Expected a unique config.PROPERTY=OPTION: " + setting)
    seen.add(key)
    prop = stack.getCommonProperty(key)
    options = [str(option) for option in jlist(prop.getOptions())]
    if options and value not in options:
        raise ValueError("Invalid option for " + key + ": " + value + "; choices: " + ", ".join(options))
    if prop.isLocked() and str(prop.getValue()) != value:
        raise ValueError("Locked property: " + key)
    changes.append((prop, str(prop.getValue()), value))

if args.apply:
    try:
        for prop, old, value in changes:
            prop.setValue(value)
            if str(prop.getValue()) != value:
                raise RuntimeError("Property was not accepted: " + str(prop.getId()))
    except Exception:
        # Do not leave a partially changed model in the warm worker.
        for prop, old, value in changes:
            if str(prop.getValue()) != old:
                prop.setValue(old)
        raise
    configuration.save()
    generateProjectContent(args.project, None)

result = {
    "project": args.project,
    "module": str(stack.getId()),
    "applied": args.apply,
    "generated": args.apply,
    "properties": [{"id": str(prop.getId()), "before": old, "requested": value,
                    "model_value": str(prop.getValue())} for prop, old, value in changes],
}
