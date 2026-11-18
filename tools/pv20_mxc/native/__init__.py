"""Native (Windows) fixture helpers shared by the PV-20 native scripts.

Card T-460. Importing this package has no side effects and touches no
system state; the Windows system calls live behind the small injectable
functions in common.py so the unit tests run on Linux with fakes.
"""
