"""Provide interactive menus for flight management and summary reporting.

Menu handlers accept database_path (the SQLite file) and return None unless
documented otherwise. They collect input before calling transactional database
helpers. SQLite errors and business-rule ValueError propagate to main, which
reports them without exiting the menu. EOFError/KeyboardInterrupt propagate
from input prompts to main's graceful-exit handler.
"""

from datetime import datetime
import re
import sqlite3
from typing import Optional, Sequence

import database as db


STATUSES = ("On Time", "Delayed", "Arrived", "Cancelled")
DATE_FORMAT = "%Y-%m-%d %H:%M"


def print_table(
	headers: Sequence[str], rows: Sequence[Sequence[object]],
) -> None:
	"""Print an aligned table, or an explicit message for an empty result."""
	if not rows:
		print("No records found.")
		return
	# Size each column from both its heading and all displayed values.
	text_rows = [[str(value) for value in row] for row in rows]
	widths = [
		max(len(header), *(len(row[index]) for row in text_rows))
		for index, header in enumerate(headers)
	]
	print(" | ".join(
		header.ljust(width) for header, width in zip(headers, widths)
	))
	print("-+-".join("-" * width for width in widths))
	for row in text_rows:
		print(" | ".join(
			value.ljust(width) for value, width in zip(row, widths)
		))


def prompt_text(label: str) -> str:
	"""Prompt with label and return stripped, nonempty printable text.

	Retry invalid input; allow EOFError/KeyboardInterrupt to signal exit.
	"""
	while True:
		value = input(label).strip()
		if value and value.isprintable():
			return value
		print("Enter a nonempty value without control characters.")


def prompt_choice(label: str, choices: Sequence[str]) -> str:
	"""Prompt with label until input matches choices; return its string value."""
	while True:
		choice = input(label).strip()
		if choice in choices:
			return choice
		print(f"Choose one of: {', '.join(choices)}.")


def prompt_record_id(
	label: str, records: Sequence[sqlite3.Row], primary_key: str,
	excluded_id: Optional[int] = None,
) -> int:
	"""Return an integer ID chosen from records using primary_key.

	label is the input prompt. excluded_id prevents selecting the other crew
	member. Unknown IDs and nonnumeric input are retried rather than written.
	"""
	valid_ids = {row[primary_key] for row in records}
	while True:
		try:
			record_id = int(input(label).strip())
		except ValueError:
			print("Enter a numeric ID from the displayed list.")
			continue
		if record_id not in valid_ids:
			print("That ID is not in the displayed list.")
		elif record_id == excluded_id:
			print("Captain and First Officer must be different pilots.")
		else:
			return record_id


def prompt_datetime(label: str) -> datetime:
	"""Prompt with label and return a naive datetime in YYYY-MM-DD HH:MM form.

	Retry invalid calendar dates and noncanonical formatting. No timezone
	conversion or comparison with the current time is performed.
	"""
	while True:
		value = input(f"{label} (YYYY-MM-DD HH:MM): ").strip()
		try:
			parsed = datetime.strptime(value, DATE_FORMAT)
			# Round-trip validation also enforces zero-padded date/time fields.
			if parsed.strftime(DATE_FORMAT) == value:
				return parsed
		except ValueError:
			pass
		print("Enter a valid date and time, for example 2026-10-15 08:30.")


def show_destinations(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
) -> list[sqlite3.Row]:
	"""Display destinations from database_path; return list[sqlite3.Row]."""
	destinations = db.list_records("Destinations", database_path)
	print("\nDestinations")
	print_table(
		("ID", "Airport", "City", "Country"),
		[(row["destination_id"], row["airport_code"], row["city"],
		  row["country"]) for row in destinations],
	)
	return destinations


def show_pilots(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
) -> list[sqlite3.Row]:
	"""Display pilots from database_path; return list[sqlite3.Row] for selection."""
	pilots = db.list_records("Pilots", database_path)
	print("\nPilots")
	print_table(
		("ID", "Name", "Licence Number"),
		[(row["pilot_id"], f"{row['first_name']} {row['last_name']}",
		  row["licence_number"]) for row in pilots],
	)
	return pilots


def view_flights(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
	flights: Optional[list[sqlite3.Row]] = None,
) -> list[sqlite3.Row]:
	"""Display flight details and return the displayed list[sqlite3.Row].

	Read all flights from database_path when flights is None; an explicitly
	empty list remains empty. Resolve destination and crew names for display.
	"""
	if flights is None:
		flights = db.list_records("Flights", database_path)
	destinations = {
		row["destination_id"]: f"{row['city']} ({row['airport_code']})"
		for row in db.list_records("Destinations", database_path)
	}
	pilots = {
		row["pilot_id"]: f"{row['first_name']} {row['last_name']}"
		for row in db.list_records("Pilots", database_path)
	}
	crew = {
		(row["flight_id"], row["role"]): pilots.get(
			row["pilot_id"], "Unknown pilot"
		)
		for row in db.list_records("Flight_Pilots", database_path)
	}
	print("\nFlights")
	print_table(
		("ID", "Flight", "Destination", "Scheduled Departure",
		 "Actual Departure", "Intended Arrival", "ETA", "Status",
		 "Captain", "First Officer"),
		[(
			row["flight_id"], row["flight_number"],
			destinations.get(row["destination_id"], "Unknown destination"),
			row["scheduled_departure"],
			row["actual_departure"] if row["actual_departure"] else "-",
			row["intended_arrival"],
			row["eta"] if row["eta"] is not None else "-", row["status"],
			crew.get((row["flight_id"], "Captain"), "Unassigned"),
			crew.get((row["flight_id"], "First Officer"), "Unassigned"),
		) for row in flights],
	)
	return flights


def schedule_flight(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
) -> None:
	"""Collect validated details and atomically save a flight and complete crew.

	Use database_path for listings and writes. Return None; database errors
	and booking conflicts are reported by the main menu's exception handlers.
	"""
	destinations = show_destinations(database_path)
	pilots = show_pilots(database_path)
	if not destinations or len(pilots) < 2:
		print("Scheduling requires a destination and at least two pilots.")
		return
	destination_id = prompt_record_id(
		"Destination ID: ", destinations, "destination_id"
	)
	while True:
		flight_number = prompt_text("Flight number: ").upper()
		if re.fullmatch(r"[A-Z0-9]+", flight_number):
			break
		print("Use only letters and digits for the flight number.")
	departure = prompt_datetime("Scheduled departure")
	while True:
		arrival = prompt_datetime("Intended arrival")
		if arrival > departure:
			break
		print("Intended arrival must be later than scheduled departure.")
	captain_id = prompt_record_id("Captain ID: ", pilots, "pilot_id")
	first_officer_id = prompt_record_id(
		"First Officer ID: ", pilots, "pilot_id", excluded_id=captain_id
	)
	# No record is written until all prompts complete; the helper saves the crew
	# and flight together or rolls back both if validation fails.
	flight_id = db.create_flight(
		destination_id, flight_number,
		departure.isoformat(sep=" "), arrival.isoformat(sep=" "),
		captain_id, first_officer_id, database_path=database_path,
	)
	print(f"Flight {flight_number} scheduled successfully (ID {flight_id}).")


def change_flight_status(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
) -> None:
	"""Update a flight in database_path, requiring ETA when choosing Delayed.

	Return None. Other statuses retain any stored ETA. Status and ETA are
	submitted as one update so a failure cannot save only one of the fields.
	"""
	flights = view_flights(database_path)
	if not flights:
		return
	flight_id = prompt_record_id("Flight ID: ", flights, "flight_id")
	for index, status in enumerate(STATUSES, start=1):
		print(f"{index}. {status}")
	choice = prompt_choice("New status: ", ("1", "2", "3", "4"))
	status = STATUSES[int(choice) - 1]
	values: dict[str, db.SQLValue] = {"status": status}
	if status == "Delayed":
		values["eta"] = prompt_datetime("ETA").isoformat(sep=" ")
	if db.update_record("Flights", flight_id, values, database_path):
		print(f"Flight {flight_id} status updated to {status}.")
	else:
		print("Flight no longer exists; no changes were made.")


def add_destination_or_pilot(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
) -> None:
	"""Run the add/back submenu for database_path; let SQLite generate IDs."""
	print("\n1. Add Destination\n2. Register Pilot\n3. Back")
	choice = prompt_choice("Choose an option: ", ("1", "2", "3"))
	if choice == "1":
		while True:
			airport_code = prompt_text("Airport code (3 letters): ").upper()
			if re.fullmatch(r"[A-Z]{3}", airport_code):
				break
			print("Airport code must contain exactly three letters.")
		record_id = db.create_record(
			"Destinations",
			{"airport_code": airport_code, "city": prompt_text("City: "),
			 "country": prompt_text("Country: ")}, database_path,
		)
		print(f"Destination added successfully (ID {record_id}).")
	elif choice == "2":
		record_id = db.create_record(
			"Pilots",
			{"first_name": prompt_text("First name: "),
			 "last_name": prompt_text("Last name: "),
			 "licence_number": prompt_text("Licence number: ")},
			database_path,
		)
		print(f"Pilot registered successfully (ID {record_id}).")


def view_flights_by_criteria(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
) -> None:
	"""Display status/destination-filtered flights from database_path.

	Return None; Back and empty destination listings leave the menu unchanged.
	"""
	print("\n1. By Status\n2. By Destination\n3. Back")
	choice = prompt_choice("Filter: ", ("1", "2", "3"))
	if choice == "1":
		for index, status in enumerate(STATUSES, start=1):
			print(f"{index}. {status}")
		selected = prompt_choice("Status: ", ("1", "2", "3", "4"))
		flights = db.filter_flights(
			status=STATUSES[int(selected) - 1], database_path=database_path
		)
	elif choice == "2":
		destinations = show_destinations(database_path)
		if not destinations:
			return
		destination_id = prompt_record_id(
			"Destination ID: ", destinations, "destination_id"
		)
		flights = db.filter_flights(
			destination_id=destination_id, database_path=database_path
		)
	else:
		return
	view_flights(database_path, flights)


def edit_flight_information(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
) -> None:
	"""Edit flight details in database_path without changing its key or crew.

	Return None. Collect planned departure/arrival together; optional actual
	departure and ETA may be cleared. The helper checks bookings before commit.
	"""
	flights = view_flights(database_path)
	if not flights:
		return
	flight_id = prompt_record_id("Flight ID: ", flights, "flight_id")
	print(
		"\n1. Scheduled Departure & Intended Arrival\n"
		"2. Actual Departure\n3. ETA\n4. Destination\n"
		"5. Flight Number\n6. Back"
	)
	choice = prompt_choice("Update: ", ("1", "2", "3", "4", "5", "6"))
	values: dict[str, db.SQLValue] = {}
	if choice == "1":
		departure = prompt_datetime("Scheduled departure")
		while True:
			arrival = prompt_datetime("Intended arrival")
			if arrival > departure:
				break
			print("Intended arrival must be later than scheduled departure.")
		values = {
			"scheduled_departure": departure.isoformat(sep=" "),
			"intended_arrival": arrival.isoformat(sep=" "),
		}
	elif choice in ("2", "3"):
		column = "actual_departure" if choice == "2" else "eta"
		action = prompt_choice("1. Set\n2. Clear\nChoose: ", ("1", "2"))
		values[column] = (
			prompt_datetime(column.replace("_", " ").title()).isoformat(
				sep=" "
			) if action == "1" else None
		)
	elif choice == "4":
		destinations = show_destinations(database_path)
		if not destinations:
			return
		values["destination_id"] = prompt_record_id(
			"Destination ID: ", destinations, "destination_id"
		)
	elif choice == "5":
		while True:
			number = prompt_text("Flight number: ").upper()
			if re.fullmatch(r"[A-Z0-9]+", number):
				break
			print("Use only letters and digits for the flight number.")
		values["flight_number"] = number
	else:
		return
	if db.update_flight_information(flight_id, values, database_path):
		print("Flight information updated successfully.")
	else:
		print("Flight no longer exists; no changes were made.")


def assign_or_reassign_pilot(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
) -> None:
	"""Select a role and assign a distinct, available pilot in database_path.

	Return None. Preserve the counterpart when valid; otherwise request both
	pilots for atomic crew replacement. Helper errors propagate to main.
	"""
	flights = view_flights(database_path)
	if not flights:
		return
	flight_id = prompt_record_id("Flight ID: ", flights, "flight_id")
	print("\n1. Captain\n2. First Officer\n3. Back")
	choice = prompt_choice("Role: ", ("1", "2", "3"))
	if choice == "3":
		return
	role = "Captain" if choice == "1" else "First Officer"
	pilots = show_pilots(database_path)
	if len(pilots) < 2:
		print("A complete crew requires at least two pilots.")
		return
	other = [
		row for row in db.list_records("Flight_Pilots", database_path)
		if row["flight_id"] == flight_id and row["role"] != role
	]
	if len(other) != 1:
		# Repair the entire crew rather than commit an understaffed flight.
		print("Complete crew required: select both pilots for this flight.")
		captain = prompt_record_id("Captain ID: ", pilots, "pilot_id")
		officer = prompt_record_id(
			"First Officer ID: ", pilots, "pilot_id", excluded_id=captain
		)
		db.set_flight_pilots(flight_id, captain, officer, database_path)
	else:
		pilot_id = prompt_record_id(
			"Pilot ID: ", pilots, "pilot_id", excluded_id=other[0]["pilot_id"]
		)
		db.assign_flight_pilot(flight_id, pilot_id, role, database_path)
	print("Crew assignment saved successfully.")


def view_pilot_schedule(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
) -> None:
	"""Display a pilot's assignments from database_path, including Cancelled.

	Return None. Empty pilot or assignment lists produce explicit messages.
	"""
	pilots = show_pilots(database_path)
	if not pilots:
		return
	pilot_id = prompt_record_id("Pilot ID: ", pilots, "pilot_id")
	schedule = db.get_pilot_schedule(pilot_id, database_path)
	print("\nPilot Schedule")
	print_table(
		("Flight", "Role", "Destination", "Departure", "Arrival", "Status"),
		[(row["flight_number"], row["role"],
		  f"{row['city']} ({row['airport_code']})",
		  row["scheduled_departure"], row["intended_arrival"], row["status"])
		 for row in schedule],
	)


def edit_destination_information(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
) -> None:
	"""Edit one destination field in database_path, preserving its primary key.

	Return None. Validate text/code input; SQL uniqueness errors reach main.
	"""
	destinations = show_destinations(database_path)
	if not destinations:
		return
	destination_id = prompt_record_id(
		"Destination ID: ", destinations, "destination_id"
	)
	print("\n1. Airport Code\n2. City\n3. Country\n4. Back")
	choice = prompt_choice("Field: ", ("1", "2", "3", "4"))
	if choice == "4":
		return
	column = ("airport_code", "city", "country")[int(choice) - 1]
	while True:
		value = prompt_text(f"New {column.replace('_', ' ')}: ")
		if column != "airport_code":
			break
		value = value.upper()
		if re.fullmatch(r"[A-Z]{3}", value):
			break
		print("Airport code must contain exactly three letters.")
	if db.update_destination_information(
		destination_id, {column: value}, database_path
	):
		print("Destination updated successfully.")
	else:
		print("Destination no longer exists; no changes were made.")


def view_summary_reports(
	database_path: db.DatabasePath = db.DEFAULT_DATABASE,
) -> None:
	"""Display both aggregate reports from database_path and return None.

	Include zero totals and all statuses. IDs distinguish identical names;
	an empty entity table is displayed as No records found.
	"""
	destinations = db.get_flight_counts_by_destination(database_path)
	print("\nFlights per Destination")
	print_table(
		("ID", "Destination Name", "Total Flights"),
		[(row["destination_id"], f"{row['city']} ({row['airport_code']})",
		  row["total_flights"]) for row in destinations],
	)
	pilots = db.get_pilot_flight_counts(database_path)
	print("\nFlight Load per Pilot")
	print_table(
		("ID", "Pilot Name", "Total Flights Assigned"),
		[(row["pilot_id"], f"{row['first_name']} {row['last_name']}",
		  row["total_flights_assigned"]) for row in pilots],
	)


def main(database_path: db.DatabasePath = db.DEFAULT_DATABASE) -> int:
	"""Initialize database_path and route menu choices until exit.

	Returns:
		int: Zero for normal exit/EOF/Ctrl-C; one for initialization failure.

	Handle OSError, SQLite errors, and ValueError at startup. During menu
	operations, report SQLite errors and ValueError after helper rollback.
	The CLI does not own SQL transactions; database helpers manage them.
	"""
	try:
		db.initialize_database(database_path)
	except (OSError, sqlite3.Error, ValueError) as error:
		print(f"Unable to initialize the database: {error}")
		return 1
	try:
		while True:
			# Keep existing option numbers stable, including 6 for Exit.
			print(
				"\nFlight Management System\n"
				"1. View All Flights\n"
				"2. View Destinations & Pilots\n"
				"3. Schedule a New Flight\n"
				"4. Update Flight Status\n"
				"5. Add New Destination / Pilot\n"
				"6. Exit\n"
				"\nAdditional Flight Operations\n"
				"7. View Flights by Criteria\n"
				"8. Update Flight Information\n"
				"9. Assign / Reassign Pilot to Flight\n"
				"\nPilot & Destination Operations\n"
				"10. View Pilot Schedule\n"
				"11. View / Update Destination Information\n"
				"\nReports\n"
				"12. View Summary Reports & Analytics"
			)
			choice = prompt_choice(
				"Choose an option: ",
				tuple(str(number) for number in range(1, 13)),
			)
			try:
				# Route each operation through a handler sharing database_path.
				if choice == "1":
					view_flights(database_path)
				elif choice == "2":
					show_destinations(database_path)
					show_pilots(database_path)
				elif choice == "3":
					schedule_flight(database_path)
				elif choice == "4":
					change_flight_status(database_path)
				elif choice == "5":
					add_destination_or_pilot(database_path)
				elif choice == "6":
					print("Goodbye.")
					return 0
				elif choice == "7":
					view_flights_by_criteria(database_path)
				elif choice == "8":
					edit_flight_information(database_path)
				elif choice == "9":
					assign_or_reassign_pilot(database_path)
				elif choice == "10":
					view_pilot_schedule(database_path)
				elif choice == "11":
					edit_destination_information(database_path)
				else:
					view_summary_reports(database_path)
			# Catch IntegrityError first because it is a subclass of sqlite3.Error.
			except sqlite3.IntegrityError as error:
				print(f"Could not save: duplicate or invalid data ({error}).")
			except sqlite3.Error as error:
				print(f"Database operation failed: {error}")
			except ValueError as error:
				print(f"Could not complete the operation: {error}")
	except (EOFError, KeyboardInterrupt):
		print("\nGoodbye. Any unsaved input was discarded.")
		return 0


if __name__ == "__main__":
	raise SystemExit(main())
