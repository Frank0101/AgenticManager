"""Code shared by the AgenticManager skills.

Lives in the agentic-manager-utils-lib skill, which is installed next to the
others. A script that uses it puts that skill's folder on sys.path first:

    LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                           "..", "..", "agentic-manager-utils-lib")
    sys.path.insert(0, LIB_DIR)
    from agentic_manager import config

output_folder.py and output_file.py also run as scripts, for an agent that
writes a skill's files itself.
"""
