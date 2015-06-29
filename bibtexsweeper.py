#!/usr/bin/env python

import argparse
import re
import json
import codecs

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import author


class BibTexSweeperConfig(object):
    replace            = {}
    typeAliases        = {}
    baseOutputElements = {'ID', 'ENTRYTYPE'}
    outputElements     = {}
    protectStrings     = {}
    protectElements    = {}
    etAlTreshold       = 0
    etAlIeeeMode       = 0

    @staticmethod
    def load(cfgFile):
        with open(cfgFile, 'r') as f:
            config = json.loads(f.read())
            BSC = BibTexSweeperConfig  # Abbreviation
            BSC.replace         = config.get('replace', BSC.replace)
            BSC.typeAliases     = config.get('typeAliases', BSC.typeAliases)
            BSC.outputElements  = config.get('outputElements', BSC.outputElements)
            BSC.protectStrings  = config.get('protectStrings', BSC.protectStrings)
            BSC.etAlTreshold    = config.get('etAlTreshold', BSC.etAlTreshold)
            BSC.etAlIeeeMode    = config.get('etAlIeeeMode', BSC.etAlIeeeMode)
            BSC.protectElements = config.get('protectElements', BSC.protectElements)

            """ Make sure we never filter out the 'ENTRYTYPE' and 'ID' """
            for bibType, allowedElements in BSC.outputElements.items():
                allowedElements.extend(BSC.baseOutputElements)


def iterRulesPerTypeAndKey(entries, rules, callback):
    for entry in entries:
        for bibType, elemRules in rules.items():
            if entry['ENTRYTYPE'] != bibType and bibType != "all":
                continue
            if type(elemRules) is dict:
                for elemKey, remainder in elemRules.items():
                    callback(entry, elemKey, remainder)
            else:
                callback(entry, elemRules)


def protectStringsCb(entry, elemKey, strings):
    for string in strings:
        """ Abbreviations should start with a word boundary, hence the '\W' """
        """ Note that things like "SDRAMs" will still match to the string "SDRAM" """
        rex = re.compile(r'(.*\W)' + re.escape(string) + r'(.*)', re.IGNORECASE)
        #m0 = re.match(rex, entry[elemKey])
        entry[elemKey] = re.sub(rex, r'\1{' + re.escape(string) + r'}\2', entry[elemKey])


def protectElementsCb(entry, elementsToProtect):
    for elem in elementsToProtect:
        if elem in entry:
            entry[elem] = ''.join(['{', entry[elem], '}'])


def protectElements(entries, rules):
    iterRulesPerTypeAndKey(entries, rules, protectElementsCb)


def protectStrings(entries, rules):
    iterRulesPerTypeAndKey(entries, rules, protectStringsCb)


def removeUnwantedElements(entries, rules):
    for bibType, allowedElements in rules.items():
        for i, entry in enumerate(entries):
            if entry['ENTRYTYPE'] == bibType:
                entries[i] = {key: val for key, val in entry.items() if key in allowedElements}


def replaceInEntry(entry, typeRules):
    for key, pairs in typeRules.items():
        try:
            for pair in pairs:
                assert(len(pair) == 2)
                rex = re.compile(re.escape(pair[0]), re.IGNORECASE)
                entry[key] = rex.sub(pair[1], entry[key])
        except KeyError:
            pass


def replace(entries, rules):
    """ Apply the replacement rules to the entries """
    for bibType, typeRules in rules.items():
        for entry in entries:
            if entry['ENTRYTYPE'] == bibType or bibType == "all":
                replaceInEntry(entry, typeRules)


def removeAliases(entries, rules):
    """ Remove types which are aliases for other types """
    for bibType, aliases in rules.items():
        for entry in entries:
            if entry['ENTRYTYPE'] in aliases:
                entry['ENTRYTYPE'] = bibType


def expandOptElement(entry, key):
    """ Choose the prefixed element over the regular element if it is longer """
    keyNoOpt = key[len('opt'):]
    assert(len(keyNoOpt) > 0)

    if keyNoOpt in entry:
        if len(entry[keyNoOpt]) < len(entry[key]):
            entry[keyNoOpt] = entry[key]
    else:
        entry[keyNoOpt] = entry[key]
    del entry[key]


def expandOptElements(entries):
    for entry in entries:
        for key, elem in entry.items():
            if key.startswith('opt'):
                expandOptElement(entry, key)


def checkRequiredWithList(entry, required):
    """ If the element in the 'required' list is a tuple, then at least one of the items (or)
        in the tuple needs to exist in the 'entry'.
    """
    for req in required:
        if type(req) is tuple:
            tmp = [x for x in req if x in entry]
            if len(tmp) == 0:
                """None of the required options found"""
                print('WARNING: entry %s misses required field %s.' % (entry['ID'], req))

        elif req not in entry:
            print('WARNING: entry %s (%s) misses required field %s.' % (entry['ID'], entry['title'], req))
            #import urllib
            #params = urllib.urlencode({'q': entry['title'], 'format': 'json'})
            #url = 'http://dblp.org/search/api/?'
            #f = urllib.urlopen("%s%s" % (url, params))
            #print(f.read())


def checkRequired(entries):
    requiredBase = [('organization', 'author', 'institution'), 'title']
    requiredPerType = {'inproceedings': requiredBase + ['pages', 'year', 'booktitle']}

    for entry in entries:
        req = requiredPerType.get(entry['ENTRYTYPE'], requiredBase)
        checkRequiredWithList(entry, req)


def checkEtAl(entries):
    """ Make sure et al. is not embedded in the author string """
    for entry in entries:
        try:
            if 'et al.' in entry['author']:
                print('WARNING: entry {id} contains et al. embedded in author string.'.format(id=entry['ID']))
        except KeyError:
            pass


def checkBookTitleYear(entries):
    """ Make sure there is no reference to a year in the booktitle entries """
    for entry in entries:
        try:
            title = entry['booktitle']  # KeyError exception triggers here.
            m0 = re.match(r'.*\'\d{2}.*', title)  # Quoted year, i.e. '95
            m1 = re.match(r'.*\d{4}.*', title)   # Full year
            if m0 is not None or m1 is not None:
                print('WARNING: entry {id} may contain year in booktitle ({booktitle}).'.format(id=entry['ID'], booktitle=title))

                if 'year' not in entry:
                    print('         The "year" element is free. Consider moving it there.')
                else:
                    print('         Check the "year" element. It should probably match the booktitle.')

        except KeyError:
            pass


def getBblEntries(bblFile):
    """ Returns the ids of the enties found in the bblFile, based on a simple regex """
    entries = []
    with open(bblFile, 'r') as f:
        lines = f.read()
        entries.extend(re.findall(r'\\bibitem\[.*?\]{([\w\-_]+)}', lines, flags=re.DOTALL | re.MULTILINE))
        entries.extend(re.findall(r'\\bibitem{([\w\-_]+)}', lines, flags=re.DOTALL | re.MULTILINE))
    return entries


def filterEntriesWithBbl(entries, bblFile):
    bblEntries = getBblEntries(bblFile)
    entries = [x for x in entries if x['ID'] in bblEntries]
    return entries


def applyEtAlTreshold(entries, etAlTreshold, etAlIeeeMode):
    if etAlTreshold == 0:
        return

    if etAlIeeeMode == 1:
        remainingLength = 1
    else:
        remainingLength = etAlTreshold

    for entry in entries:
        """ Apply authors customization """
        try:
            entry = author(entry)
            nAuthors = len(entry['author'])
            if nAuthors > etAlTreshold:
                """ Chop extra authors, and append 'et al.' """
                entry['author'] = entry['author'][:remainingLength]
                entry['author'][remainingLength - 1] = entry['author'][remainingLength - 1].replace(',', '~{\it{et al.}},')
            # Convert back into regular string:
            if nAuthors == 1 and entry['author'][0].split(' ') == 1:
                entry['author'][0] = '{{{author}}}'.format(author=entry['author'][0])
            entry['author'] = ' and '.join(entry['author'])
        except KeyError:
            pass


def parseArguments():
    parser = argparse.ArgumentParser(description='Bibtex file checker')
    parser.add_argument('--bib',      dest='bib',      type=str, required=True,  default=None,  help='Bibtex file')
    parser.add_argument('--bbl',      dest='bbl',      type=str, required=False, default=None,  help='bbl file. Only the entries in the bbl file will be processed.')
    parser.add_argument('--config',   dest='config',   type=str, required=False, default=None,  help='config file.')
    parser.add_argument('--out',      dest='out',      type=str, required=False, default='out.bib',  help='Target bibtex file')
    return parser.parse_args()


def main():
    args = parseArguments()

    if args.config is not None:
        if args.config == args.bib:
            args.config = args.bib + '_config.json'
        BibTexSweeperConfig.load(args.config)

    with open(args.bib, 'r') as bibfile:
        db = bibtexparser.load(bibfile)
        entries = db.entries

        if args.bbl is not None:
            entries = filterEntriesWithBbl(entries, args.bbl)

        """ Modifications """
        removeAliases(entries, BibTexSweeperConfig.typeAliases)
        expandOptElements(entries)
        replace(entries, BibTexSweeperConfig.replace)
        removeUnwantedElements(entries, BibTexSweeperConfig.outputElements)
        protectStrings(entries, BibTexSweeperConfig.protectStrings)
        protectElements(entries, BibTexSweeperConfig.protectElements)

        """ Checks """
        checkRequired(entries)
        checkEtAl(entries)
        checkBookTitleYear(entries)

        """ Apply author customization """
        applyEtAlTreshold(entries, BibTexSweeperConfig.etAlTreshold, BibTexSweeperConfig.etAlIeeeMode)

        """ Plug the entries back into the parser object. """
        db.entries = entries
        db._entries_dict = {}

        # with open('out.json', 'w') as f:
        #     f.write(json.dumps(entries))

        with codecs.open(args.out, 'w', 'utf-8') as f:
            bibtexparser.dump(db, f)

if __name__ == '__main__':
    main()
