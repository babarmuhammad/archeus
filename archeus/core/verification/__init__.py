"""P13 verification, merge-back and review (p13-design-gate).

    evidence   what the verifier observes itself: git facts and the commands
               P4's inspection found, run in the workspace, output as artifacts
    reviewer   the `review` own call: prompt, schema, independence
    worker     `archeus-verify`, the scan worker that runs all of it

It records only through `core/application/verification.py`, and it authorises,
routes and executes nothing.
"""
