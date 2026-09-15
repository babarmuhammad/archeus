//! Says what archeus is and how to install it, then exits non-zero.
//!
//! Non-zero on purpose: whoever reached this ran `cargo install archeus` and
//! did not get the tool, so the shell should not report success.

fn main() {
    eprintln!(
        "archeus is a Python program, not a Rust one.\n\
         \n\
             pipx install archeus        # or: pip install archeus\n\
         \n\
         The memory and workspace layer for AI coding agents: persistent\n\
         per-project memory, every session you have ever had, and control over\n\
         what the next one costs.\n\
         \n\
         https://github.com/babarmuhammad/archeus"
    );
    std::process::exit(1);
}
