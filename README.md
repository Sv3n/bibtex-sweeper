# bibtex-sweeper
Clean bibtex entries, fix errors, protect acronyms and more!

## Goal
The main purpose of this tool is to take a large, slightly unorganized and perhaps inconsistent bibtex file, and filter it down to a smaller consistent one, that can easily be used in publications. It essentially applies several filtering steps to achieve this goal.

## Installing
Bibtex-sweeper depends on a relatively new version of [bibtexparser](https://github.com/sciunto/python-bibtexparser.git). To install it, you can use:

```bash
sudo apt-get install python-pip
sudo pip install git+git://github.com/sciunto/python-bibtexparser.git
```

The simply clone this repo, and call the sweeper on `<my_bibtex_file>.bib`:

```bash
git clone https://github.com/Sv3n/bibtex-sweeper.git
python bibtex-sweeper/bibtexsweeper.py --bib <my_bibtex_file>.bib --out <filtered_output>.bib --config bibtex-sweeper/config.json
```
