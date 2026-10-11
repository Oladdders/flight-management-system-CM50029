# Flight Management System (CM50029)

## Project Overview

A university Flight Management System using Python and SQLite. The interactive
CLI manages destinations, pilots, flights, and two-pilot crews.

## Requirements

- Python 3.9 or newer (the code uses built-in collection type hints).
- Python's standard library only; no third-party packages are required.
- An interactive terminal, such as VS Code's integrated Terminal.

## Getting Started

1. Open an interactive terminal and enter the project directory:

```sh
cd FlightManagementSystem_CM50029
python3 --version
```

2. Optionally create an isolated environment (macOS/Linux):

```sh
python3 -m venv .venv
source .venv/bin/activate
```

3. Initialize the SQLite database:

```sh
python3 database.py
```

4. Run the CLI:

```sh
python3 main.py
```

No third-party installation is required. Initialization is also automatic on
CLI startup, so step 3 is optional. Type `1` to view flights or `12` for reports;
press Enter after each choice. Type `6` to exit.

### Running and Persistence

From the project directory, run:

```sh
python3 main.py
```

The application automatically creates and seeds the SQLite database on first
startup. To initialize it separately:

```sh
python3 database.py
```

The generated `flights.db` is stored alongside the Python files. Successful
changes persist between runs. Initialization does not drop or reseed existing
application tables; an incomplete application schema produces an error.
Initialization is not a migration mechanism for existing databases.

## CLI Features

Type a number at `Choose an option:` and press Enter. Use the Terminal tab,
not the Output panel or Debug Console.

- **1. View All Flights:** Show flight IDs/numbers, destination, scheduled and
  actual departure, intended arrival, ETA, status, and both crew names. Missing
  optional times appear as `-`; missing crew appears as `Unassigned`.
- **2. View Destinations & Pilots:** List destination IDs, airport codes,
  cities/countries, and pilot IDs, names, and licence numbers.
- **3. Schedule a New Flight:** Choose an existing destination, enter planned
  times and flight number, and select two distinct pilots for the crew.
- **4. Update Flight Status:** Select a flight and allowed status; choosing
  Delayed requires ETA input and saves both fields together.
- **5. Add New Destination / Pilot:** Register a location or pilot; generated
  IDs are never entered manually. The submenu also offers Back.
- **6. Exit:** Exit normally; Ctrl-C or end-of-input discards unsaved prompts
  without undoing earlier successful changes.
- **7. View Flights by Criteria:** Filter by status or destination, reusing
  the shared flight table. The helper also supports combining both criteria.
- **8. Update Flight Information:** Edit planned departure/arrival together,
  set/clear actual departure or ETA, or change destination/flight number.
- **9. Assign / Reassign Pilot to Flight:** Change one role while preserving
  its counterpart; request a complete replacement crew if needed. Booking
  conflicts are rejected before commit.
- **10. View Pilot Schedule:** Show a pilot's assignments in planned-time
  order with role, destination, planned times, and status, including Cancelled.
- **11. View / Update Destination Information:** Edit airport code, city,
  or country while preserving the destination ID.
- **12. View Summary Reports & Analytics:** Show Flights per Destination
  and Flight Load per Pilot with IDs, names, and integer totals.

Option 12, **View Summary Reports & Analytics**, displays flights per
destination and assigned flights per pilot. Both reports include zero totals
and all flight statuses, including Cancelled. SQL LEFT JOIN, COUNT, and GROUP BY
produce these summaries; pilot totals count distinct flights.

### Analytical Reporting

- `LEFT JOIN` retains destinations and pilots even with no matching flights.
- `COUNT(f.flight_id)` ignores unmatched NULL rows, returning zero rather than
  the one that `COUNT(*)` would report for such a join row.
- `COUNT(DISTINCT fp.flight_id)` counts a pilot's flights, not duplicate
  assignment rows potentially introduced through direct SQL.
- `GROUP BY` includes entity IDs to keep identical names separate. Totals
  include all statuses and are not limited to future flights.
- Empty entity tables display `No records found.` without failing.

Options 1-11 retain their original numbers and flows. Option 8 updates scheduled
departure and intended arrival together, and permits setting or clearing actual
departure and ETA. Status updates remain in option 4. Option 9 preserves the
other crew member; if a crew is incomplete it requests both pilots. Schedule
changes and reassignment still reject overlapping pilot bookings.

When scheduling, select an existing destination ID from the displayed list.
This references that destination; it does not create or edit its primary key.
New destinations, pilots, flights, and assignments receive automatic IDs.

Enter dates as `YYYY-MM-DD HH:MM`, for example `2026-10-15 08:30`.
Intended arrival must be later than scheduled departure. Flight numbers use
letters and digits, and airport codes use exactly three letters; the CLI
converts both to uppercase.

When choosing option 4 and status 2 (`Delayed`), enter an ETA using the same
date/time format. Status and ETA are saved together. Other status changes keep
the existing ETA. The flights table shows intended arrival and ETA, using `-`
when no ETA is stored. ETA does not change the pilot availability calculation.

## Database Features

### Entity Constraints

| Table         | SQL constraints and relationships                                                                                |
| ------------- | ---------------------------------------------------------------------------------------------------------------- |
| Destinations  | Generated integer PK; required city/country; required UNIQUE airport code.                                       |
| Pilots        | Generated integer PK; required names; required UNIQUE licence number.                                            |
| Flights       | Generated integer PK; required UNIQUE flight number; required destination FK and planned times; CHECK on status. |
| Flight_Pilots | Generated assignment PK; required flight/pilot FKs; CHECK on role.                                               |

`PRIMARY KEY AUTOINCREMENT` generates each record's ID. `NOT NULL` requires
values. `UNIQUE` prevents repeated codes/licences/flight numbers. `CHECK`
restricts statuses and roles, but SQLite's DATETIME declaration alone does not
validate calendar timestamps. Actual departure and ETA allow NULL.

Foreign keys are enabled on every helper connection. The destination reference
uses default `NO ACTION`, preventing deletion of a referenced destination.
Assignment FKs use `ON DELETE CASCADE` for both flights and pilots. Python
helpers guard assigned-pilot deletion to avoid leaving an incomplete crew.
Per-flight role/pilot uniqueness is enforced in Python, not composite SQL
UNIQUE constraints.

### Integrity and Booking Rules

- Every flight created through the helpers has one Captain and one First
  Officer, and they must be different pilots.
- Allowed statuses are `On Time`, `Delayed`, `Arrived`, and `Cancelled`.
- Airport codes, licence numbers, and flight numbers must be unique.
- Duplicate flight numbers are rejected when saving, after all flight details
  have been entered. There is no early duplicate-number prompt check.
- Pilots cannot be assigned to overlapping non-cancelled flights in either
  role. The check uses scheduled departure and intended arrival. Back-to-back
  flights are allowed; actual departure and ETA are not considered.
- Cancelling a flight releases its time slot without deleting its crew.
  Reactivation is rejected if it would cause a booking conflict.
- Flight creation and crew replacement are transactional: failures leave no
  partial flight or crew changes. The CLI reports errors and returns to its
  menu. Ctrl-C or end-of-input exits gracefully and discards unsaved input.

## Project Structure

```text
FlightManagementSystem_CM50029/
  CONTEXT.md    Developer schema, rules, API contracts, and validation
  README.md     Project evaluation and setup guide
  schema.sql    DDL and initial demonstration data
  database.py   Connections, CRUD, transactions, booking checks, reports
  main.py       Interactive menus, validation, and formatted tables
  .gitignore    Generated caches, local databases, and backups
```

| File                       | Responsibility                                                                          |
| -------------------------- | --------------------------------------------------------------------------------------- |
| [schema.sql](schema.sql)   | Four-table DDL and initial seed data.                                                   |
| [database.py](database.py) | Connections, initialization, parameterized CRUD, crew transactions, and booking checks. |
| [main.py](main.py)         | Interactive menu, input validation, and formatted tables.                               |
| [CONTEXT.md](CONTEXT.md)   | Detailed schema, business rules, and developer guidance.                                |

The seed script supplies 12 fictional destinations, 12 movie-star pilots,
12 flights, and 24 assignments.
