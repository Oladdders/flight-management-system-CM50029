# Flight Management System

## Project Overview

A university assignment implementing a Flight Management System using Python 3 and SQLite3. The system consists of a relational database and an interactive CLI for managing destinations, pilots, flights, pilot assignments, and aggregate reports.

## Core Rules & Environment

- **Database Engine:** SQLite 3
- **Language:** Python 3
- **Current Runtime Minimum:** Python 3.9
- **Foreign Keys:** SQLite foreign keys MUST be enabled explicitly on every connection via `PRAGMA foreign_keys = ON;`.
- **Code Quality:** [Type hinting](https://www.geeksforgeeks.org/python/type-hints-in-python/), [PEP 8 compliance](https://peps.python.org/pep-0008/), [docstrings](https://www.geeksforgeeks.org/python/python-docstrings/), parameterized queries (SQL injection prevention), robust error handling.
- **Documentation Standards**:
  - Every helper function in `database.py` must include a clear docstring explaining:
    - **Inputs**: Function parameters and their expected types.
    - **Outputs**: Returned rows, values, or data structures.
    - **Errors**: Any database errors or exceptions the function might raise.
    - **Transactions**: Which layer handles `commit()` or `rollback()`.
  - Ensure all CLI prompt messages and menu descriptions accurately reflect how the underlying SQL constraints and Python validation rules behave.

## Database Schema & Integrity Constraints

### 1. Destinations

- `destination_id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `airport_code`: TEXT NOT NULL UNIQUE (IATA code, e.g., 'LAX', 'LHR')
- `city`: TEXT NOT NULL
- `country`: TEXT NOT NULL

### 2. Pilots

- `pilot_id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `first_name`: TEXT NOT NULL
- `last_name`: TEXT NOT NULL
- `licence_number`: TEXT NOT NULL UNIQUE

### 3. Flights

- `flight_id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `destination_id`: INTEGER NOT NULL (FK -> Destinations.destination_id)
- `flight_number`: TEXT NOT NULL UNIQUE (e.g., 'BA123')
- `scheduled_departure`: DATETIME NOT NULL
- `actual_departure`: DATETIME NULL
- `intended_arrival`: DATETIME NOT NULL
- `eta`: DATETIME NULL
- `status`: TEXT NOT NULL CHECK(status IN ('On Time', 'Delayed', 'Arrived', 'Cancelled'))

### 4. Flight_Pilots (Junction / Associative Table)

- `assignment_id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `flight_id`: INTEGER NOT NULL (FK -> Flights.flight_id ON DELETE CASCADE)
- `pilot_id`: INTEGER NOT NULL (FK -> Pilots.pilot_id ON DELETE CASCADE)
- `role`: TEXT NOT NULL CHECK(role IN ('Captain', 'First Officer'))

- **Enforcement Boundaries**:
  - **SQL Schema Enforcement**: Basic entity integrity, foreign keys (`ON DELETE CASCADE`), primary keys, and static column checks (`role IN ('Captain', 'First Officer')`).
  - **Python Helper Enforcement**: Business logic validations—such as ensuring a single flight has distinct pilots assigned as Captain and First Officer without overlapping roles—are validated inside `database.py` transactional helpers to deliver clean CLI error messaging.

All primary keys are generated automatically. The generic CRUD helpers exclude
primary keys from permitted insert/update columns. Selecting an existing
destination or pilot ID in the CLI supplies a foreign key, not a new primary key.

## Critical Business Rules

1. Every flight MUST have two pilot assignments: exactly one **Captain** and exactly one **First Officer**.
2. A single pilot cannot be assigned to both roles on the same flight.
3. Status changes (e.g., from 'On Time' to 'Delayed') must update the database safely.
4. A pilot cannot be booked on overlapping non-cancelled flights, regardless of role. Overlap is measured from scheduled departure to intended arrival; back-to-back flights are allowed. Database helpers enforce this for creation, crew changes, schedule edits, and reactivation of cancelled flights. Actual departure and ETA do not affect this check; direct SQL bypasses it.
5. Departure and arrival must be parseable timestamps, and intended arrival must be later than scheduled departure. The CLI accepts `YYYY-MM-DD HH:MM` and stores ISO-format strings; use a consistent time basis because the CLI does not perform timezone conversion.
6. Choosing Delayed in the status CLI requires ETA input and saves status/ETA atomically. This is a user-flow requirement, not a database-wide constraint: helpers can write Delayed without an ETA and standalone ETA editing can clear it. No ETA comparison against planned arrival or current time is currently enforced.

## Enforcement Boundaries

- SQL enforces NOT NULL, primary keys, unique airport codes/licences/flight numbers, allowed statuses/roles, and foreign keys when enabled. It does not enforce crew size, role uniqueness within a flight, or distinct pilots within a flight.
- `create_flight` inserts the flight and both assignments in one transaction. `set_flight_pilots` replaces the complete crew automically. Errors roll back the entire operation.
- `_validate_flight_crew` requires exactly two assignments with roles Captain and First Officer and different pilot IDs. It runs before booking validation for crew creation/replacement, flight updates, and individual pilot-assignment updates. Violations raise `ValueError` and roll back the mutation.
- `_validate_flight_booking` runs inside write transactions after crew insertion or flight/assignment updates. It checks either pilot role against other non-cancelled flights, excludes the current flight, and raises `ValueError` naming the pilot and conflicting flight.
- Cancelling retains crew assignments but releases availability. Status reactivation checks availability again. There is no turnaround buffer or actual-departure/ETA-based availability calculation.
- `delete_record` rejects individual assignment deletion and deletion of any assigned pilot, including pilots assigned to cancelled flights. Reassign first. Flight deletion cascades to assignments; referenced destinations cannot be deleted.
- Direct SQL can bypass crew size, per-flight role/pilot uniqueness, and booking rules. In particular, the required `ON DELETE CASCADE` on pilot references can leave an understaffed flight if a pilot is deleted outside the helpers. Startup does not audit or repair existing records.

## Application Architecture

- `schema.sql`: Contains DDL table creation and initial seed data.
- `database.py`: Handles connection management, initialization, and clean parameterized CRUD functions.
- `main.py`: Interactive CLI interface providing menu-driven operations for end users.

## Initialization and Persistence

- Run `python3 main.py` for the CLI; it initializes the database automatically. Run `python3 database.py` for initialization alone.
- Default schema and database paths are resolved relative to `database.py`, not the shell working directory. The generated database is `flights.db` alongside the source files.
- `initialize_database` returns `True` when creating/seeding a database and `False` when all four application tables already exist. It rejects a partial application schema and never drops or reseeds existing application tables. It does not validate existing table definitions or perform migrations.
- The current workspace database was explicitly migrated to remove the two composite crew UNIQUE constraints, preserving records and IDs and creating a timestamped `flights.before_python_crew_rules_*.db.bak` backup. Other databases created with the older schema retain those constraints until separately migrated; initialization alone does not remove them.
- The seed script contains 12 destinations, 12 pilots, 12 flights, and 24 assignments: exactly one Captain and one First Officer per seeded flight. Destinations are fictional pop-culture locations and pilots use movie-star names.
- `get_connection` enables foreign keys and returns `sqlite3.Row` results; its caller must close the connection. Prefer `database_connection`, which commits success, rolls back failure, and always closes.

## Database API

- `create_record`: Insert destinations or pilots. Use `create_flight` for flights and `set_flight_pilots` for crews.
- `get_record` / `list_records`: Read a record by ID or list a table in primary-key order. A missing record returns `None`.
- `update_record`: Update allowlisted non-key columns. Assignment updates permit only `pilot_id`. Flight and assignment mutations undergo crew and booking validation. Returns `False` if the record does not exist.
- `delete_record`: Delete with the crew-preservation restrictions above; returns `False` if absent.
- `update_flight_status`: Update an allowed status via `update_record`.
- `filter_flights`: Parameterized filtering by status and/or destination ID.
- `get_flight_counts_by_destination`: LEFT JOIN Destinations to Flights and GROUP BY destination, counting non-null flight IDs so unused destinations return zero.
- `get_pilot_flight_counts`: LEFT JOIN Pilots to Flight_Pilots and GROUP BY pilot, counting distinct flight IDs so unassigned pilots return zero. Both summaries include all statuses and group by entity ID to keep identical names separate.
- `update_flight_information`: Validate supplied timestamp fields and delegate to the existing transactional flight update. Optional actual departure and ETA can be cleared with `None`.
- `assign_flight_pilot`: Transactionally insert or replace one role and validate the resulting complete crew and availability. Use `set_flight_pilots` when both roles need assigning.
- `get_pilot_schedule`: Join assignments, flights, and destinations in scheduled-time order; includes cancelled flights.
- `update_destination_information`: Validate printable destination fields and three-letter uppercase airport codes, then update without changing the primary key.
- All query values use parameters. Dynamic table and column names are allowlisted rather than accepted as arbitrary SQL. SQLite/file errors propagate to callers; rule violations raise `ValueError`.

## Implemented CLI

1. **View All Flights:** Aligned table with ID, flight number, destination, scheduled/actual departure, intended arrival, ETA, status, Captain, and First Officer. Missing optional times are shown as `-`; missing crew members are shown as `Unassigned`.
2. **View Destinations & Pilots:** Formatted lists with IDs, airport/city/country, pilot names, and licence numbers.
3. **Schedule a New Flight:** Select an existing destination, enter a flight number and times, then select two distinct pilots. Requires at least one destination and two pilots.
4. **Update Flight Status:** Select a flight ID and a numbered allowed status. Selecting Delayed requires a valid ETA in `YYYY-MM-DD HH:MM` format. Status and ETA are saved together with `update_record`; other status changes retain the existing ETA. This is CLI validation, not a database-wide requirement for every Delayed record.
5. **Add New Destination / Pilot:** Submenu for adding a destination, registering a pilot, or returning to the menu.
6. **Exit:** Graceful termination; Ctrl-C and EOF also discard unsaved input and exit.
7. **View Flights by Criteria:** Filter by a selected status or destination, using the shared flight table.
8. **Update Flight Information:** Edit scheduled departure and intended arrival together, set/clear actual departure or ETA, change destination, or change flight number. Status retains its original option 4 flow.
9. **Assign / Reassign Pilot to Flight:** Choose a role and a distinct pilot, preserving the other assignment. If the other role is missing or malformed, select both pilots to replace the whole crew. Booking checks remain enforced.
10. **View Pilot Schedule:** Select a pilot and display assignments with role, destination, scheduled departure/arrival, and status, including cancelled flights.
11. **View / Update Destination Information:** Display destinations, select an ID, and edit airport code, city, or country; never edit the primary key.
12. **View Summary Reports & Analytics:** Display formatted Flights per Destination and Flight Load per Pilot tables with IDs, names, and totals, including zero-flight entities. Existing options 1-11 remain unchanged.

Input validation retries invalid menu choices, unknown/non-numeric IDs, blank
or non-printable text, malformed dates, arrival-before-departure, and duplicate
pilot selections. Airport codes are three uppercase ASCII letters; flight
numbers are uppercase ASCII letters/digits. Duplicate airport codes, licences,
and flight numbers are rejected by SQLite at save time. Early duplicate-flight
number rejection was intentionally not retained.

The CLI catches `sqlite3.IntegrityError`, other SQLite errors, and `ValueError`
without crashing the menu. Booking conflicts are reported after collecting the
flight details. It does not currently expose deletion. Crew reassignment,
schedule edits, actual-departure edits, and standalone ETA edits are now
available through the appended menu options. Existing options 1-6 are intact.

## Reporting Semantics

- Destination reports count non-null matching flight IDs, not COUNT(\*), so LEFT JOIN rows with no flight return zero.
- Pilot reports count DISTINCT flight IDs, not assignment rows, to avoid inflating flight load if direct SQL created duplicate assignments.
- GROUP BY includes primary keys and descriptive fields. Names alone are not identifiers; identical names must remain separate report rows.
- Reports are historical totals across every status, not only future or active flights. Pilot schedule views likewise include cancelled assignments.
