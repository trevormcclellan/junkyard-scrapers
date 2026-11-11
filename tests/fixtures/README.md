# Parser fixtures

Most fixtures are small, synthetic regression examples derived from the existing parser
contracts, including the October 2026 LKQ markup supported by the checker. Fixtures
contain no production secrets; captured examples are documented below. They verify field mapping,
empty/error distinctions and pagination behavior; they do not prove that a live
upstream still uses this layout. Add sanitized captured examples when repairing a
new upstream change, and run a live smoke test in staging before deploying.

`upullandsave-makes.html` contains the make dropdown captured on 2026-11-10 from
https://upullandsave.com/hebron-ky/rtp-pick-a-part/inventory/, reduced to the
placeholder and three makes. It preserves the actual field name, option values,
and label whitespace. The live page and Mercedes-Benz models endpoint were also
verified when this fixture was captured.

`jacks-missing-models.html` contains five rows captured on 2026-11-10 from
https://jacksusedautoparts.com/vehicleInventory.php. It includes blank BMW and
Mercedes-Benz model cells and an identical Chevrolet row repeated by the source.
Unrelated rows and inline styles are omitted. These cases must retain vehicles
and their raw-field identities without weakening validation for other providers.
