from argparse import ArgumentParser
import sys

from tyme import TymeSheet, TymeError, parse_time, fmt_delta

PARSER = ArgumentParser(prog='tyme')
SUBPARSERS = PARSER.add_subparsers()

def command(name, *aliases):
    """Registers a function as a commandline command."""
    def decorator(func):
        parser = SUBPARSERS.add_parser(name, aliases=aliases)
        parser.set_defaults(func=func)
        func.parser = parser
        return func
    return decorator

def add_argument(*args,  **kwargs):
    """Adds commandline arguments for a command function."""
    #print(choices)
    def decorator(func):
        func.parser.add_argument(*args, **kwargs)
        return func
    return decorator


@add_argument('task', nargs='+')
@add_argument('-tag', nargs='*', )
@add_argument('-at', type=parse_time, metavar='TIME')
@command('new', 'n')
def new_cmd(sheet, args):
    task = ' '.join(args.task)
    tags = args.tag or ()
    sheet.add_task(task, tags)
    sheet.save()
    print('Created task:', task)


@add_argument('task', nargs='+')
@add_argument('-at', type=parse_time, metavar='TIME')
@command('in', 'i')
def in_cmd(sheet, args):
    query = ' '.join(args.task)
    task = sheet.find_task(query)
    sheet.clock_in(task, time=args.at)
    sheet.save()
    print('Clocked in:', task)


@add_argument('-at', type=parse_time)
@command('out', 'o')
def out_cmd(sheet, args):
    task = sheet.clock_out(time=args.at)
    sheet.save()
    print('Clocked out:', task)


@add_argument('tags', nargs='*')
@command('report', 'r')
def report_cmd(sheet, args):
    print(sheet.tag_filter(*args.tags))


@command('edit', 'e')
def edit_cmd(sheet, args):
    sheet = sheet.edit()
    sheet.save()

@command('status', 's')
def status_cmd(sheet, args):
    e = sheet.current_entry
    if e is None:
        print('No active task.')
    else:
        print('Clocked in:', e.task, fmt_delta(e.time))

@add_argument('task', nargs='+')
@add_argument('-at', type=parse_time)
@command('complete', 'c')
def complete_cmd(sheet, args):
    query = ' '.join(args.task)
    task = sheet.find_task(query)
    sheet.complete_task(task, time=args.at) 
    sheet.save()
    print('Completed:', task)

@command('undo', 'u')
def undo_cmd(sheet, args):
    backup = sheet.file + '~'
    old = TymeSheet.from_file(backup)
    old.save()
    print('Undo!')

def main():
    if len(sys.argv) == 1:
        # This should happen automatically with argparser, but it doesn't.
        sys.argv.append('-help')

    try:
        sheet = TymeSheet.from_file()
    except FileNotFoundError:
        # First time!
        sheet = TymeSheet()
    args = PARSER.parse_args()
    
    try:
        args.func(sheet, args)
    except TymeError as e:
        print('ERROR:', e)
        exit(1)

if __name__ == '__main__':
    main()