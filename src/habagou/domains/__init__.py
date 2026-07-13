"""Pure, I/O-free domain logic.

Modules in this package hold the app's core algorithms as plain functions and
dataclasses: the spaced-repetition scheduler (:mod:`habagou.domains.scheduling`)
and the daily-goal streak maths (:mod:`habagou.domains.streaks`).

Purity rule: nothing here may import the database engine, the data-access
layer, or a database session (nor perform any other I/O). Services map ORM
rows onto these dataclasses and back, which keeps the algorithms swappable and
unit testable without a database.
"""
