"""The folder a skill writes its files to: <name> in the output root the user's
config sets (output.root), or in <system temp>/agentic-manager if it sets none.

As a script it prints the folder, so the agent knows it without reading the
config. A run of a folder per subject starts with new_run(), which names it by
day and empties its place, so a rerun the same day starts from scratch and
earlier days' folders stay; later steps find it with run_folder(). A _ folder
beside the runs, such as the kept examples, is the user's own: runs read it and
none deletes it; the description.md saying what it holds is handled here.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

if not __package__:
    # Run as a script: import the package from the folder that holds it.
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.realpath(__file__))))
from agentic_manager.config import is_filled, load_config  # noqa: E402

# Where skills write their files when the config sets no output root.
TEMP_ROOT = os.path.join(tempfile.gettempdir(), "agentic-manager")
# The file that says what a _ folder holds, such as an example or an asset.
DESCRIPTION = "description.md"
# The folder beside a skill's runs that holds the examples the user kept.
KEPT_EXAMPLES = "_examples"
# Inside a run's folder, the folders that support its document: what it is
# built from but doesn't read directly, such as what the sources gave and a
# subagent's synopsis of a source, and the charts the document shows. Their _
# sets them apart from the document and the files the run reads and writes;
# unlike a _ folder beside the runs, they belong to the run.
RAW_DIR = "_raw"
CHARTS_DIR = "_charts"
# A description's title, and its labelled lines, such as **Shows:** text.
DESCRIPTION_TITLE = re.compile(r"# (.+)")
LABELLED_LINE = re.compile(r"^\*\*([^*\n]+):\*\* (.+)$", re.M)
# The name day_folder() gives, read back: its subject and its YY-MM-DD date.
DAY_FOLDER = re.compile(r"(?P<subject>.+)_(?P<date>\d\d-\d\d-\d\d)")
DAY_FORMAT = "%y-%m-%d"


def new_run(name, subject, day):
    """(folder, temporary, run, replaced) of a run starting from scratch: the
    folder `run`, <subject>_<YY-MM-DD> for `day`, created empty inside the
    skill's output folder `name`, as output_folder() gives it, after deleting
    the same subject's folder of that day, which `replaced` says was there."""
    folder, temporary = output_folder(name)
    run = day_folder(subject, day)
    path = target(folder, run)
    replaced = clear_folder(path)
    os.makedirs(path)
    return folder, temporary, run, replaced


def run_folder(name, run, kind, subject, init_script):
    """The absolute path of the existing run folder `run` inside the skill's
    output folder `name`, the folder of a `kind`, such as "deck", named
    <`subject`>_<YY-MM-DD> and made by `init_script`. Exits if `run` isn't
    such a name, would lead outside the folder or doesn't exist."""
    _run_subject(run, kind, subject)
    folder, _ = output_folder(name)
    path = target(folder, run)
    if not os.path.isdir(path):
        raise SystemExit(
            f"{run} doesn't exist in {folder}: run {init_script} first")
    return path


def run_document(run, document_kind, kind, subject):
    """The file name of the run `run`'s document, as document_name() gives it
    for the subject its folder is named after and `document_kind`, such as
    "Slides.html". Exits, as run_folder() does, if `run` isn't the name of
    the folder of a `kind`, <`subject`>_<YY-MM-DD>."""
    return document_name(_run_subject(run, kind, subject), document_kind)


def _run_subject(run, kind, subject):
    """The subject of the run folder `run`, or an exit naming the form of
    the folder of a `kind`, <`subject`>_<YY-MM-DD>."""
    found = folder_subject(run)
    if found is None:
        raise SystemExit(
            f"{run!r} is not a {kind} folder, <{subject}>_<YY-MM-DD>")
    return found


def output_folder(name):
    """(folder, temporary): the absolute folder a skill writes its files to,
    `name` in the user's output root, or in TEMP_ROOT if the config doesn't set
    one, created if missing, and whether it is that temporary one. Exits if
    `name` isn't a single folder name or the config can't be read."""
    try:
        name = folder_name(name)
    except argparse.ArgumentTypeError as error:
        raise SystemExit(str(error))
    root = output_root()
    folder, temporary = (root, False) if root else (TEMP_ROOT, True)
    folder = os.path.abspath(os.path.join(folder, name))
    os.makedirs(folder, exist_ok=True)
    return folder, temporary


def output_root():
    """The folder where skills write their files, with ~ expanded, or None if
    the config doesn't set one. Exits if the config can't be read."""
    output = load_config().get("output")
    root = output.get("root") if isinstance(output, dict) else None
    if not is_filled(root):
        return None
    return os.path.expanduser(root.strip())


def folder_name(value):
    """`value`, trimmed, if it is a single folder name, not a path; else an
    argparse error, so --name can use it as its type."""
    name = value.strip()
    if not name or name in (".", "..") or os.sep in name or (os.altsep and os.altsep in name):
        raise argparse.ArgumentTypeError(
            f"{value!r} must be a single folder name, not a path")
    return name


def document_name(subject, kind):
    """The file name of a run's document, <subject>_<kind>, such as
    "Jane-Doe_Review_Prep.md" for "Jane-Doe" and "Review_Prep.md": the
    subject its folder is named after, so every skill's documents read
    alike."""
    return f"{subject}_{kind}"


def work_folder(name, *parts):
    """The folder `parts` of the working files of the skill whose output
    folder is `name`, in the system's temporary folder: files only a run
    needs, such as subagents' tasks, kept out of the output folder so it
    holds only the skill's own files."""
    return os.path.join(tempfile.gettempdir(), name, *parts)


def target(folder, relative):
    """The absolute path of `relative` inside `folder`. Exits if it would lead
    outside the folder."""
    if not relative or os.path.isabs(relative) or os.pardir in relative.replace("\\", "/").split("/"):
        raise SystemExit(
            f"{relative!r} must be a relative path inside the output folder, without ..")
    path = os.path.join(folder, relative)
    root, resolved = os.path.realpath(folder), os.path.realpath(path)
    if resolved == root:
        raise SystemExit(
            f"{relative!r} must name a file inside the output folder")
    if os.path.commonpath([root, resolved]) != root:
        raise SystemExit(f"{relative!r} leads outside the output folder")
    return path


def day_folder(subject, day):
    """The name of a subject's folder for a day, <subject>_<YY-MM-DD>, such as
    PROJ-Sprint-3_26-03-16; `day` is a date or a datetime."""
    return f"{subject}_{day.strftime(DAY_FORMAT)}"


def folder_day(name):
    """The day of a subject's folder named by day_folder(), as a date, or
    None for a name of another form."""
    match = DAY_FOLDER.fullmatch(name)
    return datetime.strptime(match["date"], DAY_FORMAT).date() if match else None


def folder_subject(name):
    """The subject of a subject's folder named by day_folder(), or None for a
    name of another form."""
    match = DAY_FOLDER.fullmatch(name)
    return match["subject"] if match else None


def folder_problem(folder, wanted):
    """What is wrong with the files in `folder`, those starting with a dot
    aside, when they aren't the set `wanted`, or None when they are: the
    files it must hold, those to move out and those missing."""
    files = {name for name in os.listdir(folder) if not name.startswith(".")}
    if files == wanted:
        return None
    extra, missing = sorted(files - wanted), sorted(wanted - files)
    return ("the folder must hold only " + ", ".join(sorted(wanted))
            + (f"; move {', '.join(extra)} to your own scratch folder" if extra else "")
            + (f"; missing {', '.join(missing)}" if missing else ""))


def clear_folder(path):
    """Deletes `path`, a folder with everything in it, or only the link or file
    found there instead, and returns whether there was anything to delete."""
    if not os.path.lexists(path):
        return False
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)
    return True


def description(title, labelled, *more):
    """The text of a description.md that read_description() reads back: the
    `title`, each of `labelled` ({label: text}) as a **Label:** text line, then
    the paragraphs `more`."""
    lines = [f"# {title}", *(f"**{label}:** {text}" for label,
                             text in labelled.items()), *more]
    return "\n\n".join(lines) + "\n"


def read_description(path):
    """(title, {label: text}) of the description.md at `path`, such as an
    example's or an image's: empty when there is none."""
    text = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    title = DESCRIPTION_TITLE.match(text)
    return (title[1].strip() if title else "",
            {label: value.strip() for label, value in LABELLED_LINE.findall(text)})


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Print, and create, the folder a skill writes its files to.",
        epilog='Prints one line of JSON, {"folder": ..., "temporary": bool}. "temporary" is true when '
        "the config sets no output root, so the folder is in the system temp folder and may be "
        "cleared, which the skill tells the user. Fails with a message on stderr if the config "
        "can't be read or the name isn't a single folder name.")
    add_name_argument(parser)
    return parser.parse_args(argv)


def add_name_argument(parser):
    """Adds --name, the skill's output folder, to the command line `parser`."""
    parser.add_argument("--name", type=folder_name, required=True,
                        help="the name of the skill's output folder, such as tech-investigations")


def main():
    folder, temporary = output_folder(parse_args().name)
    print(json.dumps({"folder": folder, "temporary": temporary}))


if __name__ == "__main__":
    main()
