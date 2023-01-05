# sysexpect

Proof of Concept: This program analyzes your entire system, and reports any and all additions/modifications/deletions when compared with the stock data from the packet manager. In other words, it checks the "expectation" that all system files are exactly as they should be from the package manager, unmodified, without any additional or missing files.

Because I'm still exploring:
- All of this is very Debian-centric for now.
- Don't mind the code quality. If it reliably works or reports an error (instead of producing corrupt data), it's good enough.
- Usability is terrible, because I don't know what parts will be actually necessary.
- Entirely unoptimized python. That said, processing the `.deb`s is done in-memory instead of unpacking everything and spamming your disk.
- The git history isn't very legible, but each snapshot should still be reasonably useful.

## Why not just md5sums?

- MD5 is insecure, and can be easily broken. Why rely on it if there's a better alternative, SHA256? That's what this PoC uses.
- There are many more attributes: File type, non-regular files (sockets, symlinks, hardlinks(!)), permissions, file ownership
- This PoC also checks for additional files, which cannot be easily detected by an md5sums-like approach.
- Finally, apt sets the mtime of files upon installation. This PoC also checks for deviations of file mtimes, as this indicates some kind of irregularity that might be interesting.

## Usage

1. Collect one or more `.deb`s that you expect to be installed on your system. You can use `dpkg-query` and your local system cache for a first approximation.
2. Convert each `.deb` to a list of expectations: `./deb2fsexpect.py FOO.deb FOO.deb.json`
3. OPTIONAL: If you have multiple `.deb`s *AND* you want a report of all the unexpected/new files, use `./merge_expectations.py RESULT.total.json TWO_OR_MORE_SOURCES.deb.json` to merge the JSON files from the previous step.
4. Check that a given root directory satisfies all expectations: `./check_expect.py /path/to/destdir/ FOO.json`
   If you want to check the expectations against the currently-running system, just pass `/` as the first argument.
   Yes, I'm very aware that `./check_expect.py / FOO.json` looks wrong. Feel free to implement something nicer with argsparser, because I won't.