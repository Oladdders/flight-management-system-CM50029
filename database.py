"""SQLite persistence; use crew helpers to preserve complete flight crews.

Python helpers enforce distinct pilots, one assignment per role, and complete
crews. Direct SQL (including cascading pilot deletion) can bypass these crew
and booking rules; use the CRUD operations for application mutations.
"""

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Iterator, Mapping, Optional, Union


DatabasePath = Union[str, Path]
SQLValue = Union[str, int, float, bytes, None]
DEFAULT_DATABASE = Path(__file__).with_name("flights.db")
DEFAULT_SCHEMA = Path(__file__).with_name("schema.sql")

# SQL values use placeholders; identifiers must come from these allowlists.
TABLE_COLUMNS = {
	"Destinations": ("airport_code", "city", "country"),
	"Pilots": ("first_name", "last_name", "licence_number"),
	"Flights": (
		"destination_id", "flight_number", "scheduled_departure",
		"actual_departure", "intended_arrival", "eta", "status",
	),
	"Flight_Pilots": ("flight_id", "pilot_id", "role"),
}
PRIMARY_KEYS = {
	"Destinations": "destination_id",
	"Pilots": "pilot_id",
	"Flights": "flight_id",
	"Flight_Pilots": "assignment_id",
}


def get_connection(
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> sqlite3.Connection:
	"""Open a row-based connection with foreign keys enabled.

	Args:
		database_path: SQLite file path, or ':memory:' for an isolated database.

	Returns:
		An open sqlite3.Connection; the caller is responsible for closing it.

	Raises:
		sqlite3.Error: If opening or configuring the connection fails.
	"""
	connection = sqlite3.connect(str(database_path))
	try:
		connection.execute("PRAGMA foreign_keys = ON;")
		connection.row_factory = sqlite3.Row
	except sqlite3.Error:
		connection.close()
		raise
	return connection


@contextmanager
def database_connection(
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> Iterator[sqlite3.Connection]:
	"""Manage a connection and its transaction for database_path.

	Yields:
		A sqlite3.Connection with row results and enabled foreign keys.

	Raises:
		sqlite3.Error: If connection, query, or commit operations fail.
		Exception: Any exception from the caller's block, after rollback.
	"""
	connection = get_connection(database_path)
	try:
		# Connection context manages commit/rollback, but not connection closure.
		with connection:
			yield connection
	finally:
		connection.close()


def initialize_database(
	database_path: DatabasePath = DEFAULT_DATABASE,
	schema_path: DatabasePath = DEFAULT_SCHEMA,
) -> bool:
	"""Create and seed a new database; return False if already initialized.

	Existing application tables are never dropped or reseeded. An incomplete
	schema is rejected; existing definitions are not audited or migrated.

	Args:
		database_path: File to create or open.
		schema_path: UTF-8 SQL file containing DDL and seed data.

	Returns:
		bool: True after initialization, False if all application tables exist.

	Raises:
		ValueError: If only some application tables exist.
		OSError: If the schema file cannot be read.
		UnicodeError: If the schema file is not valid UTF-8.
		sqlite3.Error: If schema creation or seeding fails.
	"""
	schema = Path(schema_path).read_text(encoding="utf-8")
	with database_connection(database_path) as connection:
		existing = {
			row["name"] for row in connection.execute(
				"SELECT name FROM sqlite_master WHERE type = 'table'"
			)
		}
		application_tables = set(TABLE_COLUMNS)
		if application_tables <= existing:
			return False
		if application_tables & existing:
			raise ValueError("Database has an incomplete application schema.")
		connection.executescript(schema)
	return True


def _validate_table(table: str) -> str:
	"""Return the primary-key name for table; raise ValueError if unknown."""
	if table not in PRIMARY_KEYS:
		raise ValueError("Unknown database table.")
	return PRIMARY_KEYS[table]


def _validate_columns(table: str, values: Mapping[str, SQLValue]) -> None:
	"""Validate table and values keys; raise ValueError for empty/unknown keys."""
	_validate_table(table)
	if not values or not set(values) <= set(TABLE_COLUMNS[table]):
		raise ValueError("Supply one or more valid table columns.")


def create_record(
	table: str,
	values: Mapping[str, SQLValue],
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> int:
	"""Insert a destination or pilot and return its ID.

	Use create_flight for flights and set_flight_pilots for complete crews.
	Invalid or duplicate data raises sqlite3.IntegrityError.

	Args:
		table: Destinations or Pilots.
		values: Mapping of non-key column names to SQLite-compatible values.
		database_path: SQLite file to modify.

	Returns:
		int: Automatically generated record ID.

	Raises:
		ValueError: If the table or supplied columns are not supported.
		sqlite3.IntegrityError: If required, unique, or foreign-key data fails.
		sqlite3.Error: If another database operation fails.
		RuntimeError: If SQLite supplies no inserted record ID.
	"""
	_validate_columns(table, values)
	if table not in ("Destinations", "Pilots"):
		raise ValueError("Use the flight/crew helpers for this table.")
	columns = ", ".join(values)
	placeholders = ", ".join("?" for _ in values)
	with database_connection(database_path) as connection:
		cursor = connection.execute(
			f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
			tuple(values.values()),
		)
		if cursor.lastrowid is None:
			raise RuntimeError("Insert did not return a record ID.")
		return cursor.lastrowid


def get_record(
	table: str,
	record_id: int,
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> Optional[sqlite3.Row]:
	"""Fetch record_id from an allowlisted table in database_path.

	Returns:
		Optional[sqlite3.Row]: The matching row, or None if absent.

	Raises:
		ValueError: If table is unknown.
		sqlite3.Error: If opening or querying the database fails.
	"""
	primary_key = _validate_table(table)
	with database_connection(database_path) as connection:
		return connection.execute(
			f"SELECT * FROM {table} WHERE {primary_key} = ?", (record_id,)
		).fetchone()


def list_records(
	table: str,
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> list[sqlite3.Row]:
	"""List an allowlisted table in database_path by primary-key order.

	Returns:
		list[sqlite3.Row]: All matching rows; an empty list if none exist.

	Raises:
		ValueError: If table is unknown.
		sqlite3.Error: If opening or querying the database fails.
	"""
	primary_key = _validate_table(table)
	with database_connection(database_path) as connection:
		return connection.execute(
			f"SELECT * FROM {table} ORDER BY {primary_key}"
		).fetchall()


def update_record(
	table: str,
	record_id: int,
	values: Mapping[str, SQLValue],
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> bool:
	"""Update supplied fields; return False when the record is missing.

	Assignments permit only pilot_id updates; use set_flight_pilots to replace
	both crew members or swap roles. Constraint errors roll back the update.

	Args:
		table: Application table name from the allowlist.
		record_id: Existing primary-key value; it is never changed.
		values: Mapping of permitted columns to replacement values.
		database_path: SQLite file to modify.

	Returns:
		bool: True if one row was updated, False if the record is absent.

	Raises:
		ValueError: For invalid columns, crew, time intervals, or bookings.
		sqlite3.IntegrityError: If a SQL constraint rejects the new data.
		sqlite3.Error: If another database operation fails.
	"""
	_validate_columns(table, values)
	if table == "Flight_Pilots" and set(values) != {"pilot_id"}:
		raise ValueError("Only pilot_id may be updated on an assignment.")
	assignments = ", ".join(f"{column} = ?" for column in values)
	primary_key = PRIMARY_KEYS[table]
	with database_connection(database_path) as connection:
		cursor = connection.execute(
			f"UPDATE {table} SET {assignments} WHERE {primary_key} = ?",
			(*values.values(), record_id),
		)
		if cursor.rowcount == 1:
			if table == "Flights":
				_validate_flight_booking(connection, record_id)
			elif table == "Flight_Pilots":
				assignment = connection.execute(
					"SELECT flight_id FROM Flight_Pilots "
					"WHERE assignment_id = ?", (record_id,),
				).fetchone()
				_validate_flight_booking(connection, assignment["flight_id"])
		return cursor.rowcount == 1


def delete_record(
	table: str,
	record_id: int,
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> bool:
	"""Delete a record; return False if absent, preserving complete crews.

	Assigned pilots and individual assignments cannot be deleted. Reassign a
	pilot first. Deleting a flight cascades to its assignments; deleting a
	referenced destination raises sqlite3.IntegrityError.

	Args:
		table: Destinations, Pilots, or Flights.
		record_id: Primary-key value to delete from database_path.
		database_path: SQLite file to modify.

	Returns:
		bool: True if deleted, False if the record is absent.

	Raises:
		ValueError: If the table is invalid or deletion would remove crew.
		sqlite3.IntegrityError: If a referenced destination is deleted.
		sqlite3.Error: If another database operation fails.
	"""
	primary_key = _validate_table(table)
	if table == "Flight_Pilots":
		raise ValueError("Delete the flight or replace its complete crew.")
	with database_connection(database_path) as connection:
		connection.execute("BEGIN IMMEDIATE")
		if table == "Pilots" and connection.execute(
			"SELECT 1 FROM Flight_Pilots WHERE pilot_id = ? LIMIT 1",
			(record_id,),
		).fetchone():
			raise ValueError("Reassign this pilot's flights before deletion.")
		cursor = connection.execute(
			f"DELETE FROM {table} WHERE {primary_key} = ?", (record_id,)
		)
		return cursor.rowcount == 1


def _validate_flight_crew(
	connection: sqlite3.Connection,
	flight_id: int,
) -> None:
	"""Require one Captain and one First Officer with different pilot IDs."""
	# Roles and pilot uniqueness are Python rules, not SQL UNIQUE constraints.
	crew = connection.execute(
		"SELECT pilot_id, role FROM Flight_Pilots WHERE flight_id = ?",
		(flight_id,),
	).fetchall()
	if len(crew) != 2 or {row["role"] for row in crew} != {
		"Captain", "First Officer"
	}:
		raise ValueError("Flight must have one Captain and one First Officer.")
	if len({row["pilot_id"] for row in crew}) != 2:
		raise ValueError("Captain and First Officer must be different pilots.")


def _validate_flight_booking(
	connection: sqlite3.Connection,
	flight_id: int,
) -> None:
	"""Reject invalid intervals or overlapping non-cancelled pilot bookings.

	Scheduled departure and intended arrival define a half-open interval;
	back-to-back flights are allowed. Call inside the mutation transaction
	so failures roll back and concurrent writes cannot bypass the check.

	Args:
		connection: Open connection with a write transaction already started.
		flight_id: Flight whose crew and planned interval should be validated.

	Returns:
		None: Validation succeeds without changing data.

	Raises:
		ValueError: If crew, planned times, or pilot availability are invalid.
		sqlite3.Error: If validation queries fail.
	"""
	_validate_flight_crew(connection, flight_id)
	flight = connection.execute(
		"SELECT julianday(scheduled_departure) AS departure, "
		"julianday(intended_arrival) AS arrival FROM Flights "
		"WHERE flight_id = ?", (flight_id,),
	).fetchone()
	if (
		flight is None or flight["departure"] is None
		or flight["arrival"] is None
		or flight["arrival"] <= flight["departure"]
	):
		raise ValueError("Flight needs valid departure and later arrival times.")
	# Half-open intervals overlap only when each start precedes the other end.
	conflict = connection.execute(
		"SELECT p.first_name, p.last_name, other.flight_number "
		"FROM Flights current "
		"JOIN Flight_Pilots crew ON crew.flight_id = current.flight_id "
		"JOIN Pilots p ON p.pilot_id = crew.pilot_id "
		"JOIN Flight_Pilots booked ON booked.pilot_id = crew.pilot_id "
		"JOIN Flights other ON other.flight_id = booked.flight_id "
		"WHERE current.flight_id = ? "
		"AND other.flight_id != current.flight_id "
		"AND current.status != 'Cancelled' "
		"AND other.status != 'Cancelled' "
		"AND julianday(current.scheduled_departure) "
		"< julianday(other.intended_arrival) "
		"AND julianday(other.scheduled_departure) "
		"< julianday(current.intended_arrival) "
		"ORDER BY other.flight_id, p.pilot_id LIMIT 1", (flight_id,),
	).fetchone()
	if conflict is not None:
		raise ValueError(
			f"Pilot {conflict['first_name']} {conflict['last_name']} "
			f"is already booked on overlapping flight "
			f"{conflict['flight_number']}."
		)


def _insert_crew(
	connection: sqlite3.Connection,
	flight_id: int,
	captain_id: int,
	first_officer_id: int,
) -> None:
	"""Insert exactly one assignment per role using distinct pilots.

	If captain_id equals first_officer_id, raise ValueError.
	connection must belong to the caller's transaction; this helper does not
	commit. SQL errors and booking/crew ValueError propagate for rollback.
	"""
	if captain_id == first_officer_id:
		raise ValueError("Captain and First Officer must be different pilots.")
	connection.executemany(
		"INSERT INTO Flight_Pilots (flight_id, pilot_id, role) VALUES (?, ?, ?)",
		(
			(flight_id, captain_id, "Captain"),
			(flight_id, first_officer_id, "First Officer"),
		),
	)
	_validate_flight_booking(connection, flight_id)


def create_flight(
	destination_id: int,
	flight_number: str,
	scheduled_departure: str,
	intended_arrival: str,
	captain_id: int,
	first_officer_id: int,
	status: str = "On Time",
	actual_departure: Optional[str] = None,
	eta: Optional[str] = None,
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> int:
	"""Atomically create a flight and its crew; return the flight ID.

	Use ISO-format date/time strings. Any invalid flight or crew data rolls
	back the entire operation, leaving no partially staffed flight.
	Overlapping non-cancelled pilot bookings raise ValueError.

	Args:
		destination_id: Existing destination primary key.
		flight_number: Unique flight identifier.
		scheduled_departure: Planned departure as an ISO-format string.
		intended_arrival: Planned arrival, strictly later than departure.
		captain_id: Existing pilot selected as Captain.
		first_officer_id: Different existing pilot selected as First Officer.
		status: Allowed status; defaults to On Time.
		actual_departure: Optional recorded departure string, or None.
		eta: Optional estimated arrival string, or None.
		database_path: SQLite file to modify.

	Returns:
		int: Automatically generated flight ID.

	Raises:
		ValueError: If crew, planned times, or availability are invalid.
		sqlite3.IntegrityError: If uniqueness, foreign keys, or CHECK fail.
		sqlite3.Error: If another database operation fails.
		RuntimeError: If SQLite supplies no inserted flight ID.
	"""
	with database_connection(database_path) as connection:
		cursor = connection.execute(
			"INSERT INTO Flights (destination_id, flight_number, "
			"scheduled_departure, intended_arrival, status, "
			"actual_departure, eta) VALUES (?, ?, ?, ?, ?, ?, ?)",
			(destination_id, flight_number, scheduled_departure,
			 intended_arrival, status, actual_departure, eta),
		)
		flight_id = cursor.lastrowid
		if flight_id is None:
			raise RuntimeError("Insert did not return a flight ID.")
		# Crew validation occurs before the enclosing transaction can commit.
		_insert_crew(connection, flight_id, captain_id, first_officer_id)
		return flight_id


def set_flight_pilots(
	flight_id: int,
	captain_id: int,
	first_officer_id: int,
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> None:
	"""Atomically replace a flight's crew, restoring the old crew on failure.

	Args:
		flight_id: Existing flight to staff.
		captain_id: Pilot ID for the Captain role.
		first_officer_id: Different pilot ID for the First Officer role.
		database_path: SQLite file to modify.

	Returns:
		None: Both assignments are saved on success.

	Raises:
		ValueError: If flight, crew, planned times, or availability are invalid.
		sqlite3.IntegrityError: If either pilot does not exist.
		sqlite3.Error: If another database operation fails.
	"""
	with database_connection(database_path) as connection:
		# Reserve the write transaction before reading and replacing the crew.
		connection.execute("BEGIN IMMEDIATE")
		if not connection.execute(
			"SELECT 1 FROM Flights WHERE flight_id = ?", (flight_id,)
		).fetchone():
			raise ValueError("Flight does not exist.")
		connection.execute(
			"DELETE FROM Flight_Pilots WHERE flight_id = ?", (flight_id,)
		)
		_insert_crew(connection, flight_id, captain_id, first_officer_id)


def update_flight_status(
	flight_id: int,
	status: str,
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> bool:
	"""Set status for flight_id in database_path using transactional CRUD.

	Returns:
		bool: True if updated, False if the flight is absent.

	Raises:
		ValueError: If crew or booking validation fails, including reactivation.
		sqlite3.IntegrityError: If status is not an allowed CHECK value.
		sqlite3.Error: If another database operation fails.

	This helper changes only status; the CLI separately requires ETA for Delayed.
	"""
	return update_record("Flights", flight_id, {"status": status}, database_path)


def filter_flights(
	status: Optional[str] = None,
	destination_id: Optional[int] = None,
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> list[sqlite3.Row]:
	"""Return flights matching optional status and destination filters.

	Args:
		status: Allowed status, or None to accept all statuses.
		destination_id: Destination primary key, or None for all destinations.
		database_path: SQLite file to query.

	Returns:
		list[sqlite3.Row]: Matching Flights rows ordered by ID, possibly empty.

	Raises:
		ValueError: If a supplied status is unknown.
		sqlite3.Error: If opening or querying the database fails.
	"""
	if status is not None and status not in (
		"On Time", "Delayed", "Arrived", "Cancelled"
	):
		raise ValueError("Unknown flight status.")
	with database_connection(database_path) as connection:
		return connection.execute(
			"SELECT * FROM Flights WHERE (? IS NULL OR status = ?) "
			"AND (? IS NULL OR destination_id = ?) ORDER BY flight_id",
			(status, status, destination_id, destination_id),
		).fetchall()


def update_flight_information(
	flight_id: int,
	values: Mapping[str, SQLValue],
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> bool:
	"""Update flight fields atomically, validating supplied timestamps.

	Args:
		flight_id: Existing flight primary key, never edited.
		values: Permitted flight fields and replacement values. Timestamp
			strings must parse as ISO format; actual_departure/eta allow None.
		database_path: SQLite file to modify.

	Returns:
		bool: True if updated, False if the flight is absent.

	Raises:
		ValueError: If fields, dates, crew, or bookings are invalid.
		sqlite3.IntegrityError: If a SQL constraint rejects the update.
		sqlite3.Error: If another database operation fails.
	"""
	_validate_columns("Flights", values)
	for column in (
		"scheduled_departure", "actual_departure", "intended_arrival", "eta"
	):
		if column in values:
			value = values[column]
			if value is None and column in ("actual_departure", "eta"):
				continue
			if not isinstance(value, str):
				raise ValueError(f"{column} must be an ISO date/time string.")
			try:
				datetime.fromisoformat(value)
			except ValueError:
				raise ValueError(f"Invalid date/time for {column}.") from None
	return update_record("Flights", flight_id, values, database_path)


def assign_flight_pilot(
	flight_id: int,
	pilot_id: int,
	role: str,
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> None:
	"""Assign or replace one role, preserving a complete, available crew.

	Args:
		flight_id: Existing flight primary key.
		pilot_id: Existing pilot to assign to the selected role.
		role: Captain or First Officer.
		database_path: SQLite file to modify.

	Returns:
		None: Assignment saved after crew and booking validation.

	Raises:
		ValueError: If role, flight, crew, interval, or availability is invalid.
		sqlite3.IntegrityError: If pilot_id does not reference a pilot.
		sqlite3.Error: If another database operation fails.

	A missing role may be inserted only if a valid counterpart already exists;
	use set_flight_pilots to create or repair an entire crew.
	"""
	if role not in ("Captain", "First Officer"):
		raise ValueError("Unknown pilot role.")
	with database_connection(database_path) as connection:
		connection.execute("BEGIN IMMEDIATE")
		if not connection.execute(
			"SELECT 1 FROM Flights WHERE flight_id = ?", (flight_id,)
		).fetchone():
			raise ValueError("Flight does not exist.")
		cursor = connection.execute(
			"UPDATE Flight_Pilots SET pilot_id = ? "
			"WHERE flight_id = ? AND role = ?", (pilot_id, flight_id, role),
		)
		if cursor.rowcount == 0:
			connection.execute(
				"INSERT INTO Flight_Pilots (flight_id, pilot_id, role) "
				"VALUES (?, ?, ?)", (flight_id, pilot_id, role),
			)
		_validate_flight_booking(connection, flight_id)


def get_pilot_schedule(
	pilot_id: int,
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> list[sqlite3.Row]:
	"""Return all assignments, including cancelled flights, in time order.

	Args:
		pilot_id: Pilot primary key to match in assignment rows.
		database_path: SQLite file to query.

	Returns:
		list[sqlite3.Row]: Flight fields plus role, city, and airport_code,
			ordered by scheduled departure. Empty for no matching assignments.

	Raises:
		sqlite3.Error: If opening or querying the database fails.
	"""
	with database_connection(database_path) as connection:
		return connection.execute(
			"SELECT f.*, fp.role, d.city, d.airport_code "
			"FROM Flight_Pilots fp JOIN Flights f "
			"ON f.flight_id = fp.flight_id JOIN Destinations d "
			"ON d.destination_id = f.destination_id WHERE fp.pilot_id = ? "
			"ORDER BY julianday(f.scheduled_departure), f.flight_id",
			(pilot_id,),
		).fetchall()


def update_destination_information(
	destination_id: int,
	values: Mapping[str, SQLValue],
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> bool:
	"""Edit destination fields without changing its generated primary key.

	Args:
		destination_id: Existing destination primary key.
		values: airport_code, city, and/or country replacement strings.
		database_path: SQLite file to modify.

	Returns:
		bool: True if updated, False if the destination is absent.

	Raises:
		ValueError: For unknown fields, blank/control text, or invalid codes.
		sqlite3.IntegrityError: If airport_code duplicates an existing code.
		sqlite3.Error: If another database operation fails.
	"""
	_validate_columns("Destinations", values)
	for column, value in values.items():
		if (
			not isinstance(value, str) or not value.strip()
			or not value.isprintable()
		):
			raise ValueError(f"{column} must be nonempty printable text.")
		if column == "airport_code" and (
			len(value) != 3 or not value.isascii()
			or not value.isalpha() or not value.isupper()
		):
			raise ValueError("Airport code must be three uppercase letters.")
	return update_record("Destinations", destination_id, values, database_path)


def get_flight_counts_by_destination(
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> list[sqlite3.Row]:
	"""Count flights of all statuses per destination, including zero totals.

	Args:
		database_path: SQLite file to query.

	Returns:
		list[sqlite3.Row]: Destination fields plus integer total_flights,
			ordered by destination ID. Empty if there are no destinations.

	Raises:
		sqlite3.Error: If opening or querying the database fails.

	LEFT JOIN retains unused destinations. COUNT(f.flight_id) ignores the
	NULL joined row and therefore returns zero, unlike COUNT(*). GROUP BY
	includes the primary key so destinations sharing a city remain separate.
	"""
	with database_connection(database_path) as connection:
		return connection.execute(
			"SELECT d.destination_id, d.airport_code, d.city, d.country, "
			"COUNT(f.flight_id) AS total_flights FROM Destinations d "
			"LEFT JOIN Flights f ON f.destination_id = d.destination_id "
			"GROUP BY d.destination_id, d.airport_code, d.city, d.country "
			"ORDER BY d.destination_id"
		).fetchall()


def get_pilot_flight_counts(
	database_path: DatabasePath = DEFAULT_DATABASE,
) -> list[sqlite3.Row]:
	"""Count distinct assigned flights per pilot, including zero totals.

	Args:
		database_path: SQLite file to query.

	Returns:
		list[sqlite3.Row]: Pilot fields plus integer total_flights_assigned,
			ordered by pilot ID. Empty if there are no pilots.

	Raises:
		sqlite3.Error: If opening or querying the database fails.

	LEFT JOIN retains unassigned pilots; COUNT ignores NULL flight IDs.
	DISTINCT counts a flight once even if direct SQL added duplicate
	assignments. GROUP BY includes pilot ID to separate identical names.
	All statuses, including Cancelled, contribute to the assigned-flight load.
	"""
	with database_connection(database_path) as connection:
		return connection.execute(
			"SELECT p.pilot_id, p.first_name, p.last_name, p.licence_number, "
			"COUNT(DISTINCT fp.flight_id) AS total_flights_assigned "
			"FROM Pilots p LEFT JOIN Flight_Pilots fp "
			"ON fp.pilot_id = p.pilot_id "
			"GROUP BY p.pilot_id, p.first_name, p.last_name, p.licence_number "
			"ORDER BY p.pilot_id"
		).fetchall()


if __name__ == "__main__":
	try:
		initialized = initialize_database()
	except (OSError, sqlite3.Error, ValueError) as error:
		raise SystemExit(f"Database initialization failed: {error}") from error
	print("Database initialized." if initialized else "Database already exists.")
