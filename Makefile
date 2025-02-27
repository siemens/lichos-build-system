bindir=/usr/bin

all:

install:
	install -D -m 755 lichoscli.py $(DESTDIR)$(bindir)/lichoscli

clean:

.PHONY: all install
