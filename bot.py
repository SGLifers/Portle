"""Entry point for hosts whose startup panel requires a Python filename."""
import sys
from portle.__main__ import main


if __name__=='__main__':
    if len(sys.argv)==1:sys.argv.append('bot')
    raise SystemExit(main())
