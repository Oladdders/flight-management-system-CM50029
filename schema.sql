-- Enable foreign keys before starting the atomic schema-and-seed transaction.
PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- Destinations use generated integer primary keys and unique airport codes.
-- Required location fields have NOT NULL constraints; no FK or CHECK applies.
CREATE TABLE Destinations (
	destination_id INTEGER PRIMARY KEY AUTOINCREMENT,
	airport_code TEXT NOT NULL UNIQUE,
	city TEXT NOT NULL,
	country TEXT NOT NULL
);

-- Pilots use generated primary keys and unique, required licence numbers.
-- Names are required; pilot records have no foreign keys or CHECK constraints.
CREATE TABLE Pilots (
	pilot_id INTEGER PRIMARY KEY AUTOINCREMENT,
	first_name TEXT NOT NULL,
	last_name TEXT NOT NULL,
	licence_number TEXT NOT NULL UNIQUE
);

-- Each flight has a generated primary key and unique, required flight number.
-- The destination FK uses default NO ACTION: referenced destinations cannot
-- be deleted. CHECK restricts status; optional actual departure/ETA allow NULL.
-- Valid time ordering and crew availability are checked by Python helpers.
CREATE TABLE Flights (
	flight_id INTEGER PRIMARY KEY AUTOINCREMENT,
	destination_id INTEGER NOT NULL,
	flight_number TEXT NOT NULL UNIQUE,
	scheduled_departure DATETIME NOT NULL,
	actual_departure DATETIME,
	intended_arrival DATETIME NOT NULL,
	eta DATETIME,
	status TEXT NOT NULL
		CHECK (status IN ('On Time', 'Delayed', 'Arrived', 'Cancelled')),
	FOREIGN KEY (destination_id) REFERENCES Destinations(destination_id)
);

-- Each assignment has its own generated primary key and two required FKs.
-- ON DELETE CASCADE removes assignments when a flight or pilot is deleted.
-- CHECK limits roles to Captain/First Officer; Python, not SQL uniqueness,
-- requires one of each role with different pilots. Use helpers for mutations.
CREATE TABLE Flight_Pilots (
	assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
	flight_id INTEGER NOT NULL,
	pilot_id INTEGER NOT NULL,
	role TEXT NOT NULL CHECK (role IN ('Captain', 'First Officer')),
	FOREIGN KEY (flight_id) REFERENCES Flights(flight_id) ON DELETE CASCADE,
	FOREIGN KEY (pilot_id) REFERENCES Pilots(pilot_id) ON DELETE CASCADE
);

-- Seed 12 pop-culture destinations with illustrative three-letter codes.
INSERT INTO Destinations (airport_code, city, country) VALUES
	('GTH', 'Gotham City', 'USA'),
	('WAK', 'Wakanda', 'Africa'),
	('ATL', 'Atlantis', 'Atlantic'),
	('HOG', 'Hogwarts', 'UK'),
	('TAT', 'Tatooine', 'Outer Rim'),
	('SHR', 'The Shire', 'Middle-earth'),
	('NAR', 'Cair Paravel', 'Narnia'),
	('SPR', 'Springfield', 'USA'),
	('ARK', 'Arendelle', 'Arendelle'),
	('PAN', 'Pandora', 'Alpha Centauri'),
	('HIL', 'Hill Valley', 'USA'),
	('EMR', 'Emerald City', 'Oz');

-- Seed 12 movie-star names with unique demonstration licence numbers.
INSERT INTO Pilots (first_name, last_name, licence_number) VALUES
	('Tom', 'Cruise', 'LIC001'),
	('Keanu', 'Reeves', 'LIC002'),
	('Harrison', 'Ford', 'LIC003'),
	('Leonardo', 'DiCaprio', 'LIC004'),
	('Sigourney', 'Weaver', 'LIC005'),
	('Viola', 'Davis', 'LIC006'),
	('Denzel', 'Washington', 'LIC007'),
	('Meryl', 'Streep', 'LIC008'),
	('Michelle', 'Yeoh', 'LIC009'),
	('Morgan', 'Freeman', 'LIC010'),
	('Cate', 'Blanchett', 'LIC011'),
	('Samuel', 'Jackson', 'LIC012');

-- Seed 12 flights spanning all allowed statuses and optional timestamp states.
-- References assume a newly initialized database with IDs starting at one.
INSERT INTO Flights (
	destination_id, flight_number, scheduled_departure, actual_departure,
	intended_arrival, eta, status
) VALUES
	(1, 'PC101', '2026-10-11 08:00:00', NULL,
	 '2026-10-11 10:00:00', NULL, 'On Time'),
	(2, 'PC102', '2026-10-11 08:30:00', '2026-10-11 09:15:00',
	 '2026-10-11 13:30:00', '2026-10-11 14:15:00', 'Delayed'),
	(3, 'PC103', '2026-10-10 06:00:00', '2026-10-10 06:00:00',
	 '2026-10-10 09:00:00', '2026-10-10 09:00:00', 'Arrived'),
	(4, 'PC104', '2026-10-11 09:00:00', NULL,
	 '2026-10-11 10:30:00', NULL, 'Cancelled'),
	(5, 'PC105', '2026-10-12 10:00:00', NULL,
	 '2026-10-12 18:00:00', NULL, 'On Time'),
	(6, 'PC106', '2026-10-12 11:00:00', NULL,
	 '2026-10-12 15:00:00', '2026-10-12 16:00:00', 'Delayed'),
	(7, 'PC107', '2026-10-13 07:00:00', NULL,
	 '2026-10-13 10:00:00', NULL, 'On Time'),
	(8, 'PC108', '2026-10-13 08:00:00', NULL,
	 '2026-10-13 10:00:00', NULL, 'On Time'),
	(9, 'PC109', '2026-10-10 12:00:00', '2026-10-10 12:10:00',
	 '2026-10-10 14:00:00', '2026-10-10 14:10:00', 'Arrived'),
	(10, 'PC110', '2026-10-14 06:00:00', NULL,
	 '2026-10-14 18:00:00', NULL, 'Cancelled'),
	(11, 'PC111', '2026-10-14 09:00:00', NULL,
	 '2026-10-14 12:00:00', NULL, 'On Time'),
	(12, 'PC112', '2026-10-14 10:00:00', NULL,
	 '2026-10-14 13:00:00', '2026-10-14 13:45:00', 'Delayed');

-- Seed 24 assignments: exactly two distinct pilots and one of each role/flight.
INSERT INTO Flight_Pilots (flight_id, pilot_id, role) VALUES
	(1, 1, 'Captain'), (1, 2, 'First Officer'),
	(2, 3, 'Captain'), (2, 4, 'First Officer'),
	(3, 5, 'Captain'), (3, 6, 'First Officer'),
	(4, 7, 'Captain'), (4, 8, 'First Officer'),
	(5, 9, 'Captain'), (5, 10, 'First Officer'),
	(6, 11, 'Captain'), (6, 12, 'First Officer'),
	(7, 2, 'Captain'), (7, 3, 'First Officer'),
	(8, 4, 'Captain'), (8, 5, 'First Officer'),
	(9, 6, 'Captain'), (9, 7, 'First Officer'),
	(10, 8, 'Captain'), (10, 9, 'First Officer'),
	(11, 10, 'Captain'), (11, 11, 'First Officer'),
	(12, 12, 'Captain'), (12, 1, 'First Officer');

COMMIT;
