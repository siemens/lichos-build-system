bindir=/usr/bin
pkgdatadir=/usr/share/lichoscli

all:

test:
	python3-coverage run --source=src -m pytest -vv && python3-coverage report

install:
	install -D -m 755 src/lichoscli.py $(DESTDIR)$(pkgdatadir)/lichoscli.py
	install -D -m 755 src/lichosrebuildtool.py $(DESTDIR)$(pkgdatadir)/lichosrebuildtool.py
	mkdir -p $(DESTDIR)$(bindir)
	for i in lichoscli lichosrebuildtool; do ln -s --relative $(DESTDIR)$(pkgdatadir)/$$i.py $(DESTDIR)$(bindir)/$$i; done

clean:

.PHONY: all install test
