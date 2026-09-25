"""repo-ratchet - keep raising what each repository can do, one round at a time.

A ratchet only turns one way. This package measures a repository's current
capacity, ranks where the headroom is, and records what was actually done and
actually verified, so the next round starts above the last one instead of
repeating it.

Nothing here decides *what* the improvement should be. It measures, ranks,
and refuses to record work that was not verified.
"""

__version__ = "0.2.0"
