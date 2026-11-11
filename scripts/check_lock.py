"""Fail CI when any installed runtime/build dependency is absent from the locks."""
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def main():
    root = Path(__file__).resolve().parent.parent
    locked = {}
    for filename in ('requirements.txt', 'requirements-build.txt'):
        for line in (root / filename).read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            req = Requirement(line)
            specs = list(req.specifier)
            if len(specs) != 1 or specs[0].operator != '==' or '*' in specs[0].version:
                raise SystemExit(f'{filename}: {req.name} must have an exact version pin')
            locked[canonicalize_name(req.name)] = specs[0].version
    for name, version in locked.items():
        dist = metadata.distribution(name)
        if dist.version != version:
            raise SystemExit(f'{name}: installed {dist.version}, expected {version}')
        for requirement in dist.requires or []:
            req = Requirement(requirement)
            if req.marker and not req.marker.evaluate({'extra': ''}):
                continue
            dependency = canonicalize_name(req.name)
            if dependency not in locked:
                raise SystemExit(f'{name} requires {req.name}, which is missing from the lock')
            if locked[dependency] not in req.specifier:
                raise SystemExit(f'{name} requires {req}, but lock pins {locked[dependency]}')
    print(f'Validated {len(locked)} runtime/build pins and their active dependency closure')


if __name__ == '__main__':
    main()
