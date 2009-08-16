#!/usr/bin/python
# -*- coding: utf-8  -*-
# This file is part of cjklib.
#
# cjklib is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# cjklib is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with cjklib.  If not, see <http://www.gnu.org/licenses/>.

"""
Provides the building methods for the cjklib package.

Some L{TableBuilder} implementations aren't used by the CJK library but are
provided here for additional usage.
"""

import types
import re
import os.path
import copy
import xml.sax
import csv

from sqlalchemy import Table, Column, Integer, String, Text, Index
from sqlalchemy import select, union
from sqlalchemy.sql import text, func
from sqlalchemy.sql import or_
from sqlalchemy.exc import IntegrityError, OperationalError

from cjklib import characterlookup
from cjklib import exception
from cjklib.build import warn

# pylint: disable-msg=E1101
#  member variables are set by setattr()

#{ TableBuilder and generic classes

class TableBuilder(object):
    """
    TableBuilder provides the abstract layout for classes that build a distinct
    table.
    """
    PROVIDES = ''
    """Contains the name of the table provided by this module."""
    DEPENDS = []
    """Contains the names of the tables needed for the build process."""

    def __init__(self, **options):
        """
        Constructs the TableBuilder.

        @param options: extra options
        @keyword dbConnectInst: instance of a L{DatabaseConnector}
        @keyword dataPath: optional list of paths to the data file(s)
        @keyword quiet: if C{True} no status information will be printed to
            stderr
        """
        self.db = options.get('dbConnectInst')
        for option, defaultValue in self.getDefaultOptions().items():
            optionValue = options.get(option, defaultValue)
            if not hasattr(optionValue, '__call__'):
                setattr(self, option, copy.deepcopy(optionValue))
            else:
                setattr(self, option, optionValue)

    @classmethod
    def getDefaultOptions(cls):
        """
        Returns the table builder's default options.

        The base class' implementation returns an empty dictionary. The keyword
        'dbConnectInst' is not regarded a configuration option of the operator
        and is thus not included in the dict returned.

        @rtype: dict
        @return: the reading operator's default options.
        """
        return {'dataPath': [], 'quiet': False}

    @classmethod
    def getOptionMetaData(cls, option):
        """
        Gets metadata on a given option.

        Keys can come from the subset of:
            - type: string, int, bool, ...
            - action: action as used by I{optparse}, extended by
                C{appendResetDefault}
            - choices: allowed values
            - description: short description of option

        @rtype: dict
        @return: dictionary of metadata
        """
        optionsMetaData = {'dataPath': {'type': 'pathstring',
                'action': 'extendResetDefault',
                'description': "path to data files"},
            'quiet': {'type': 'bool',
                'description': "don't print anything on stdout"}}
        return optionsMetaData[option]

    def build(self):
        """
        Build the table provided by the TableBuilder.

        Methods should raise an IOError if reading a data source fails. The
        L{DatabaseBuilder} knows how to handle this case and is able to proceed.
        """
        pass

    def remove(self):
        """
        Removes the table provided by the TableBuilder from the database.
        """
        # get drop table statement
        table = Table(self.PROVIDES, self.db.metadata)
        table.drop()
        # remove table from metadata so that recreating a table with a different
        #   schema won't raise an exception. Especially for tables created via
        #   plain sql create command
        self.db.metadata.remove(table)

    def findFile(self, fileNames, fileType=None):
        """
        Tries to locate a file with a given list of possible file names under
        the classes default data paths.

        For each file name every given path is checked and the first match is
        returned.

        @type fileNames: str/list of str
        @param fileNames: possible file names
        @type fileType: str
        @param fileType: textual type of file used in error msg
        @rtype: str
        @return: path to file of first match in search for existing file
        @raise IOError: if no file found
        """
        if type(fileNames) != type([]):
            fileNames = [fileNames]
        for fileName in fileNames:
            for path in self.dataPath:
                filePath = os.path.join(os.path.expanduser(path), fileName)
                if os.path.exists(filePath):
                    return filePath
        if fileType == None:
            fileType = "file"
        raise IOError(
            "No %s found for '%s' under path(s) '%s' for file names '%s'" \
                % (fileType, self.PROVIDES, "', '".join(self.dataPath),
                    "', '".join(fileNames)))

    def buildTableObject(self, tableName, columns, columnTypeMap=None,
        primaryKeys=None):
        """
        Returns a SQLAlchemy Table object.

        @type tableName: str
        @param tableName: name of table
        @type columns: list of str
        @param columns: column names
        @type columnTypeMap: dict of str and object
        @param columnTypeMap: mapping of column name to SQLAlchemy Column
        @type primaryKeys: list of str
        @param primaryKeys: list of primary key columns
        """
        columnTypeMap = columnTypeMap or {}
        primaryKeys = primaryKeys or []

        table = Table(tableName, self.db.metadata)
        for column in columns:
            if column in columnTypeMap:
                colType = columnTypeMap[column]
            else:
                colType = Text()
                if not self.quiet:
                    warn("column %s has no type, assuming default 'Text()'"
                        % column)
            table.append_column(Column(column, colType,
                primary_key=(column in primaryKeys), autoincrement=False))

        return table

    def buildIndexObjects(self, tableName, indexKeyList):
        """
        Returns a SQLAlchemy Table object.

        @type tableName: str
        @param tableName: name of table
        @type indexKeyList: list of list of str
        @param indexKeyList: a list of key combinations
        @rtype: object
        @return: SQLAlchemy Index
        """
        indexList = []
        table = Table(tableName, self.db.metadata, autoload=True)
        for indexKeyColumns in indexKeyList:
            indexName = tableName + '__' + '_'.join(indexKeyColumns)
            indexList.append(Index(indexName,
                *[table.c[column] for column in indexKeyColumns]))

        return indexList


class EntryGeneratorBuilder(TableBuilder):
    """
    Implements an abstract class for building a table from a generator
    providing entries.
    """
    COLUMNS = []
    """Columns that will be built"""
    PRIMARY_KEYS = []
    """Primary keys of the created table"""
    INDEX_KEYS = []
    """Index keys (not unique) of the created table"""
    COLUMN_TYPES = {}
    """Column types for created table"""

    def getGenerator(self):
        """
        Returns the entry generator.
        Needs to be implemented by child classes.
        """
        pass

    def getEntryDict(self, generator):
        entryList = []

        firstEntry = generator.next()
        if type(firstEntry) == type(dict()):
            entryList.append(firstEntry)

            for newEntry in generator:
                entryList.append(newEntry)
        else:
            firstEntryDict = dict([(column, firstEntry[i]) \
                for i, column in enumerate(self.COLUMNS)])
            entryList.append(firstEntryDict)

            for newEntry in generator:
                entryDict = dict([(column, newEntry[i]) \
                    for i, column in enumerate(self.COLUMNS)])
                entryList.append(entryDict)

        return entryList

    def build(self):
        # get generator, might raise an Exception if source not found
        generator = self.getGenerator()

        # get create statement
        table = self.buildTableObject(self.PROVIDES, self.COLUMNS,
            self.COLUMN_TYPES, self.PRIMARY_KEYS)
        table.create()

        # write table content
        #try:
            #entries = self.getEntryDict(self.getGenerator())
            #self.db.execute(table.insert(), entries)
        #except IntegrityError, e:
            #warn(unicode(e))
            ##warn(unicode(insertStatement))
            #raise

        for newEntry in generator:
            try:
                table.insert(newEntry).execute()
            except IntegrityError, e:
                if not(self.quiet):
                    warn(unicode(e))
                raise

        for index in self.buildIndexObjects(self.PROVIDES, self.INDEX_KEYS):
            index.create()


class ListGenerator:
    """A simple generator for a given list of elements."""
    def __init__(self, entryList):
        """
        Initialises the ListGenerator.

        @type entryList: list of str
        @param entryList: user defined entry
        """
        self.entryList = entryList

    def generator(self):
        for entry in self.entryList:
            yield entry

#}
#{ Unihan character information

class UnihanGenerator:
    """
    Regular expression matching one entry in the Unihan database
    (e.g. C{U+8682  kMandarin       MA3 MA1 MA4}).
    """
    keySet = None
    """Set of keys of the Unihan table."""

    ENTRY_REGEX = re.compile(ur"U\+([0-9A-F]+)\s+(\w+)\s+(.+)\s*$")

    UNIHAN_FILE_MEMBERS = ['Unihan_DictionaryIndices.txt',
        'Unihan_DictionaryLikeData.txt', 'Unihan_NormativeProperties.txt',
        'Unihan_NumericValues.txt', 'Unihan_OtherMappings.txt',
        'Unihan_RadicalStrokeCounts.txt', 'Unihan_Readings.txt',
        'Unihan_Variants.txt']

    def __init__(self, fileNames, useKeys=None, wideBuild=False, quiet=False):
        """
        Constructs the UnihanGenerator.

        @type fileNames: list of str
        @param fileNames: paths to the Unihan database files
        @type useKeys: list
        @param useKeys: if given only these keys will be read from the table,
            otherwise all keys will be returned
        @type wideBuild: bool
        @param wideBuild: if C{True} characters outside the I{BMP} will be
            included.
        @type quiet: bool
        @param quiet: if true no status information will be printed to stderr
        """
        self.fileNames = fileNames
        self.wideBuild = wideBuild
        self.quiet = quiet
        if useKeys != None:
            self.limitKeys = True
            self.keySet = set(useKeys)
        else:
            self.limitKeys = False

    def generator(self):
        """
        Iterates over the Unihan entries.

        The character definition is converted to the character's representation,
        all other data is given as is. These are merged into one entry for each
        character.
        """
        handleDict = self.getHandles()
        handleReadBuffer = {}
        # current entry goes here
        entryIndex = -1
        entry = {}

        while True:
            # synchronize all handles of sorted code points, break if we read
            #   past the current entryIndex
            for fileName, handle in handleDict.items():
                # check if we already red something from the current handle
                if fileName in handleReadBuffer:
                    redIndex, key, value = handleReadBuffer[fileName]
                    if entryIndex == redIndex:
                        entry[key] = value
                        del handleReadBuffer[fileName]
                    else:
                        # the red index is greater than our current one, skip
                        assert entryIndex < redIndex, "File '%s' is not sorted"
                        continue

                # we can read further into the current handle
                for line in handle:
                    if line.startswith('#') or line.strip() == '':
                        continue

                    resultObj = self.ENTRY_REGEX.match(line)
                    if not resultObj:
                        if not self.quiet:
                            warn("Can't read line from '%s': '%s'"
                                % (fileName, line))
                        continue
                    unicodeHexCodePoint, key, value = resultObj.group(1, 2, 3)
                    redIndex = int(unicodeHexCodePoint, 16)
                    # skip characters outside the BMP, i.e. for Chinese
                    #   characters >= 0x20000 unless wideBuild is specified
                    if not self.wideBuild and redIndex >= int('20000', 16):
                        continue
                    # if we have a limited target key set, check if the current
                    #   one is to be included
                    if self.limitKeys and not key in self.keySet:
                        continue
                    # check if we found data for the current entryIndex
                    if redIndex == entryIndex:
                        entry[key] = value
                    else:
                        handleReadBuffer[fileName] = (redIndex, key, value)
                        # we red past our current entry
                        break
                else:
                    # reached end of file
                    if fileName not in handleReadBuffer:
                        # our buffer is empty and file end reached, remove
                        handleDict[fileName].close()
                        del handleDict[fileName]

            if entryIndex >= 0:
                char = unichr(entryIndex)
                yield(char, entry)

            # if the read buffer is empty, all files are finished
            if not handleReadBuffer:
                break

            # next entry with smallest index
            entryIndex = min(
                [redIndex for redIndex, _, _ in handleReadBuffer.values()])
            entry = {}

    def getHandles(self):
        """ 
        Returns a list of handles of the Unihan database files.

        @rtype: dict
        @return: dictionary of names and handles of the Unihan files
        """
        handles = {}
        import zipfile
        if len(self.fileNames) == 1 and zipfile.is_zipfile(self.fileNames[0]):
            import StringIO
            z = zipfile.ZipFile(self.fileNames[0], "r")
            for member in z.namelist():
                handles[member] \
                    = StringIO.StringIO(z.read(member).decode('utf-8'))
        else:
            import codecs
            for member in self.fileNames:
                handles[member] = codecs.open(member, 'r', 'utf-8')
        return handles

    def keys(self):
        """
        Returns all keys read for the Unihan table.

        If the whole table is read a seek through the file is needed first to
        find all keys, otherwise the predefined set is returned.

        @rtype: list of str
        @return: list of column names
        """
        if not self.keySet:
            if not self.quiet:
                warn("Looking for all keys in Unihan database...")
            self.keySet = set()
            handleDict = self.getHandles()
            for handle in handleDict.values():
                for line in handle:
                    # ignore comments
                    if line.startswith('#'):
                        continue
                    resultObj = self.ENTRY_REGEX.match(line)
                    if not resultObj:
                        continue

                    _, key, _ = resultObj.group(1, 2, 3)
                    self.keySet.add(key)
                handle.close()
        return list(self.keySet)


class UnihanBuilder(EntryGeneratorBuilder):
    """
    Builds the Unihan database from the Unihan file provided by Unicode. By
    default only chooses characters from the X{Basic Multilingual Plane}
    (X{BMP}) with code values between U+0000 and U+FFFF.

    Windows versions of Python by default are I{narrow build}s and don't support
    characters outside the 16 bit range. MySQL < 6 doesn't support true UTF-8,
    and uses a Version with max 3 bytes:
    U{http://dev.mysql.com/doc/refman/6.0/en/charset-unicode.html}.
    """
    class EntryGenerator:
        """Generates the entries of the Unihan table."""

        def __init__(self, unihanGenerator):
            """
            Initialises the EntryGenerator.

            @type unihanGenerator: instance
            @param unihanGenerator: a L{UnihanGenerator} instance
            """
            self.unihanGenerator = unihanGenerator

        def generator(self):
            """Provides all data of one character per entry."""
            columns = self.unihanGenerator.keys()
            for char, entryDict in self.unihanGenerator.generator():
                newEntryDict = {UnihanBuilder.CHARACTER_COLUMN: char}
                for column in columns:
                    if entryDict.has_key(column):
                        newEntryDict[column] = entryDict[column]
                    else:
                        newEntryDict[column] = None
                yield newEntryDict

    PROVIDES = 'Unihan'
    CHARACTER_COLUMN = 'ChineseCharacter'
    """Name of column for Chinese character key."""
    COLUMN_TYPES = {CHARACTER_COLUMN: String(1), 'kCantonese': Text(),
        'kFrequency': Integer(), 'kHangul': Text(), 'kHanyuPinlu': Text(),
        'kJapaneseKun': Text(), 'kJapaneseOn': Text(), 'kKorean': Text(),
        'kMandarin': Text(), 'kRSJapanese': Text(), 'kRSKanWa': Text(),
        'kRSKangXi': Text(), 'kRSKorean': Text(),
        'kSimplifiedVariant': Text(), 'kTotalStrokes': Integer(),
        'kTraditionalVariant': Text(), 'kVietnamese': Text(),
        'kZVariant': Text(), 'kGB0': String(4), 'kBigFive': String(4),
        'kXHC1983': Text(), 'kHanyuPinyin': Text(), 'kIICore': Text(),
        'kSemanticVariant': Text(), 'kSpecializedSemanticVariant': Text(),
        'kCompatibilityVariant': Text()}

    PRIMARY_KEYS = [CHARACTER_COLUMN]

    INCLUDE_KEYS = ['kCompatibilityVariant', 'kCantonese', 'kFrequency',
        'kHangul', 'kHanyuPinlu', 'kJapaneseKun', 'kJapaneseOn', 'kMandarin',
        'kRSJapanese', 'kRSKanWa', 'kRSKangXi', 'kRSKorean', 'kSemanticVariant',
        'kSimplifiedVariant', 'kSpecializedSemanticVariant', 'kTotalStrokes',
        'kTraditionalVariant', 'kVietnamese', 'kXHC1983', 'kZVariant',
        'kIICore', 'kGB0', 'kBigFive', 'kHanyuPinyin']
    """Keys included in a slim version if explicitly specified."""

    def __init__(self, **options):
        """
        Constructs the UnihanBuilder.

        @param options: extra options
        @keyword dbConnectInst: instance of a L{DatabaseConnector}
        @keyword dataPath: optional list of paths to the data file(s)
        @keyword quiet: if C{True} no status information will be printed to
            stderr
        @keyword wideBuild: if C{True} characters outside the I{BMP} will be
            included.
        @keyword slimUnihanTable: if C{True} a limited set of columns specified
            by L{INCLUDE_KEYS} will be supported.
        """
        super(UnihanBuilder, self).__init__(**options)

        self.unihanGenerator = None

    @classmethod
    def getDefaultOptions(cls):
        options = super(UnihanBuilder, cls).getDefaultOptions()
        options.update({'wideBuild': False, 'slimUnihanTable': False})

        return options

    @classmethod
    def getOptionMetaData(cls, option):
        optionsMetaData = {'wideBuild': {'type': 'bool',
                'description': "include characters outside the Unicode BMP"},
            'slimUnihanTable': {'type': 'bool',
                'description': "limit keys of Unihan table"}}

        if option in optionsMetaData:
            return optionsMetaData[option]
        else:
            return super(UnihanBuilder, cls).getOptionMetaData(option)

    def getUnihanGenerator(self):
        """
        Returns the L{UnihanGenerator}. Constructs it if needed.

        @rtype: instance
        @return: instance of a L{UnihanGenerator}
        """
        if not self.unihanGenerator:
            fileNames = UnihanGenerator.UNIHAN_FILE_MEMBERS[:]
            fileNames.extend(['Unihan.zip', 'Unihan.txt'])
            path = self.findFile(fileNames, "Unihan database file(s)")
            if self.slimUnihanTable:
                columns = self.INCLUDE_KEYS
            else:
                columns = None

            # check for multiple file names (Unicode >= 5.2)
            pathList = []
            if path.endswith(('Unihan.zip', 'Unihan.txt')):
                pathList = [path]
            else:
                dirname = os.path.dirname(path)
                for fileName in UnihanGenerator.UNIHAN_FILE_MEMBERS:
                    filePath = os.path.join(dirname, fileName)
                    if os.path.exists(filePath):
                        pathList.append(filePath)
                assert(len(pathList) > 0)

            self.unihanGenerator = UnihanGenerator(pathList, useKeys=columns,
                wideBuild=self.wideBuild, quiet=self.quiet)
            if not self.quiet:
                warn("reading file(s) '%s'" % "', '".join(pathList))
        return self.unihanGenerator

    def getGenerator(self):
        return UnihanBuilder.EntryGenerator(self.getUnihanGenerator())\
            .generator()

    def build(self):
        generator = self.getUnihanGenerator()
        self.COLUMNS = [self.CHARACTER_COLUMN]
        self.COLUMNS.extend(generator.keys())

        EntryGeneratorBuilder.build(self)


class Kanjidic2Builder(EntryGeneratorBuilder):
    """
    Builds the Kanjidic database from the Kanjidic2 XML file
    U{http://www.csse.monash.edu.au/~jwb/kanjidic2/}.
    """
    class XMLHandler(xml.sax.ContentHandler):
        """Extracts a list of given tags."""
        def __init__(self, entryList, tagDict):
            xml.sax.ContentHandler.__init__(self)
            self.entryList = entryList
            self.tagDict = tagDict

            self.currentElement = []
            self.targetTag = None
            self.targetTagTopElement = None

        def endElement(self, name):
            assert(len(self.currentElement) > 0)
            assert(self.currentElement[-1] == name)
            self.currentElement.pop()

            if name == self.targetTagTopElement:
                self.targetTag = None
                self.targetTagTopElement = None

            if name == 'character':
                entryDict = {}
                for tag, function in self.tagDict.values():
                    if tag in self.currentEntry:
                        entryDict[tag] = function(self.currentEntry[tag])
                self.entryList.append(entryDict)

        def characters(self, content):
            if self.targetTag:
                if self.targetTag not in self.currentEntry:
                    self.currentEntry[self.targetTag] = []
                self.currentEntry[self.targetTag].append(content)

        def startElement(self, name, attrs):
            self.currentElement.append(name)
            if name == 'character':
                self.currentEntry = {}
            else:
                if 'character' in self.currentElement:
                    idx = self.currentElement.index('character') + 1
                    tagHierachy = tuple(self.currentElement[idx:])

                    key = (tagHierachy, frozenset(attrs.items()))
                    if key in self.tagDict:
                        self.targetTagTopElement = name
                        self.targetTag, _ = self.tagDict[key]

    class KanjidicGenerator:
        """Generates the KANJIDIC table."""
        def __init__(self, dataPath, tagDict, wideBuild=False):
            """
            Initialises the KanjidicGenerator.

            @type dataPath: list of str
            @param dataPath: optional list of paths to the data file(s)
            @type tagDict: dict
            @param tagDict: a dictionary mapping xml tag paths and attributes
                to a Column and a conversion function
            @type wideBuild: bool
            @param wideBuild: if C{True} characters outside the I{BMP} will be
                included.
            """
            self.dataPath = dataPath
            self.tagDict = tagDict
            self.wideBuild = wideBuild

        def getHandle(self):
            """
            Returns a handle of the KANJIDIC database file.

            @rtype: file
            @return: file handle of the KANJIDIC file
            """
            import gzip
            if self.dataPath.endswith('.gz'):
                import StringIO
                z = gzip.GzipFile(self.dataPath, 'r')
                handle = StringIO.StringIO(z.read())
            else:
                import codecs
                handle = codecs.open(self.dataPath, 'r')
            return handle

        def generator(self):
            """Provides a pronunciation and a path to the audio file."""
            entryList = []
            xmlHandler = Kanjidic2Builder.XMLHandler(entryList, self.tagDict)

            saxparser = xml.sax.make_parser()
            saxparser.setContentHandler(xmlHandler)
            ## don't check DTD as this raises an exception
            #saxparser.setFeature(xml.sax.handler.feature_external_ges, False)
            saxparser.parse(self.getHandle())

            for entry in entryList:
                if self.wideBuild or 'ChineseCharacter' not in entry \
                    or ord(entry['ChineseCharacter']) < int('20000', 16):
                    yield(entry)

    PROVIDES = 'Kanjidic'
    CHARACTER_COLUMN = 'ChineseCharacter'
    """Name of column for Chinese character key."""
    COLUMN_TYPES = {CHARACTER_COLUMN: String(1), 'NelsonRadical': Integer(),
        'CharacterJapaneseOn': Text(), 'CharacterJapaneseKun': Text()}
    KANJIDIC_TAG_MAPPING = {
        (('literal', ), frozenset()): ('ChineseCharacter', lambda x: x[0]),
        (('radical', 'rad_value'),
            frozenset([('rad_type', 'nelson_c')])): ('NelsonCRadical',
                lambda x: int(x[0])),
        (('radical', 'rad_value'),
            frozenset([('rad_type', 'nelson_n')])): ('NelsonNRadical',
                lambda x: int(x[0])),
        # TODO On and Kun reading in KANJIDICT include further optional
        #   attributes that makes the method miss the entry:
        #   on_type and r_status, these are currently not implemented in the
        #   file though
        (('reading_meaning', 'rmgroup', 'reading'),
            frozenset([('r_type', 'ja_on')])): ('CharacterJapaneseOn',
                ','.join),
        (('reading_meaning', 'rmgroup', 'reading'),
            frozenset([('r_type', 'ja_kun')])): ('CharacterJapaneseKun',
                ','.join),
        #(('reading_meaning', 'rmgroup', 'reading'),
            #frozenset([('r_type', 'pinyin')])): ('Pinyin',
                #lambda x: ','.join(x)),
        (('misc', 'rad_name'), frozenset()): ('RadicalName', ','.join),
        (('reading_meaning', 'rmgroup', 'meaning'), frozenset()): \
            ('Meaning_en', '/'.join),
        (('reading_meaning', 'rmgroup', 'meaning'),
            frozenset([('m_lang', 'fr')])): ('Meaning_fr', '/'.join),
        (('reading_meaning', 'rmgroup', 'meaning'),
            frozenset([('m_lang', 'es')])): ('Meaning_es', '/'.join),
        (('reading_meaning', 'rmgroup', 'meaning'),
            frozenset([('m_lang', 'pt')])): ('Meaning_pt', '/'.join),
        }
    """
    Dictionary of tag keys mapping to a table column including a function
    generating a string out of a list of entries given from the KANJIDIC entry.
    The tag keys constist of a tuple giving the xml element hierarchy below the
    'character' element and a set of attribute value pairs.
    """

    def __init__(self, **options):
        """
        Constructs the Kanjidic2Builder.

        @param options: extra options
        @keyword dbConnectInst: instance of a L{DatabaseConnector}
        @keyword dataPath: optional list of paths to the data file(s)
        @keyword quiet: if C{True} no status information will be printed to
            stderr
        @keyword wideBuild: if C{True} characters outside the I{BMP} will be
            included.
        """
        super(Kanjidic2Builder, self).__init__(**options)
        tags = [tag for tag, _ in self.KANJIDIC_TAG_MAPPING.values()]
        self.COLUMNS = tags
        self.PRIMARY_KEYS = [self.CHARACTER_COLUMN]

    @classmethod
    def getDefaultOptions(cls):
        options = super(Kanjidic2Builder, cls).getDefaultOptions()
        options.update({'wideBuild': False})

        return options

    @classmethod
    def getOptionMetaData(cls, option):
        optionsMetaData = {'wideBuild': {'type': 'bool',
                'description': "include characters outside the Unicode BMP"}}

        if option in optionsMetaData:
            return optionsMetaData[option]
        else:
            return super(Kanjidic2Builder, cls).getOptionMetaData(option)

    def getGenerator(self):
        """
        Returns the L{KanjidicGenerator}.

        @rtype: instance
        @return: instance of a L{KanjidicGenerator}
        """
        path = self.findFile(['kanjidic2.xml.gz', 'kanjidic2.xml'],
            "KANJIDIC2 XML file")
        if not self.quiet:
            warn("reading file '" + path + "'")
        return Kanjidic2Builder.KanjidicGenerator(path,
            self.KANJIDIC_TAG_MAPPING).generator()


class UnihanDerivedBuilder(EntryGeneratorBuilder):
    """
    Provides an abstract class for building a table with a relation between a
    Chinese character and another column using the Unihan database.
    """
    DEPENDS = ['Unihan']

    COLUMN_SOURCE = None
    """
    Unihan table column providing content for the table. Needs to be overwritten
    in subclass.
    """
    COLUMN_TARGETS = None
    """
    Column names for new data in created table. Needs to be overwritten in
    subclass.
    """
    COLUMN_TARGETS_TYPES = {}
    """Types of column for new data in created table."""
    GENERATOR_CLASS = None
    """
    Class defining the iterator for creating the table's data. The constructor
    needs to take two parameters for the list of entries from the Unihan
    database and the 'quiet' flag. Needs to be overwritten in subclass.
    """

    def __init__(self, **options):
        """
        Constructs the UnihanDerivedBuilder.

        @param options: extra options
        @keyword dbConnectInst: instance of a L{DatabaseConnector}
        @keyword dataPath: optional list of paths to the data file(s)
        @keyword quiet: if C{True} no status information will be printed to
            stderr
        @keyword ignoreMissing: if C{True} a missing source column will be
            ignored and a empty table will be built.
        """
        super(UnihanDerivedBuilder, self).__init__(**options)
        # create name mappings
        self.COLUMNS = ['ChineseCharacter']
        self.COLUMNS.extend(self.COLUMN_TARGETS)
        # set column types
        self.COLUMN_TYPES = {'ChineseCharacter': String(1)}
        self.COLUMN_TYPES.update(self.COLUMN_TARGETS_TYPES)

    @classmethod
    def getDefaultOptions(cls):
        options = super(UnihanDerivedBuilder, cls).getDefaultOptions()
        options.update({'ignoreMissing': True})

        return options

    @classmethod
    def getOptionMetaData(cls, option):
        optionsMetaData = {'ignoreMissing': {'type': 'bool',
                'description': \
                    "ignore missing Unihan column and build empty table"}}

        if option in optionsMetaData:
            return optionsMetaData[option]
        else:
            return super(UnihanDerivedBuilder, cls).getOptionMetaData(option)

    def getGenerator(self):
        # create generator
        table = self.db.tables['Unihan']
        if self.COLUMN_SOURCE in table.c:
            tableEntries = self.db.selectRows(
                select([table.c.ChineseCharacter, table.c[self.COLUMN_SOURCE]],
                    table.c[self.COLUMN_SOURCE] != None))
        elif self.ignoreMissing:
            tableEntries = []
            if not self.quiet:
                warn("Column '%s' does not exist in source 'Unihan', ignoring"
                    % self.COLUMN_SOURCE)
        else:
            raise IOError("Column '%s' does not exist in source 'Unihan'"
                % self.COLUMN_SOURCE)
        return self.GENERATOR_CLASS(tableEntries, self.quiet).generator()

    def build(self):
        if not self.quiet:
            warn("Reading table content from Unihan column '%s'"
                % self.COLUMN_SOURCE)
        super(UnihanDerivedBuilder, self).build()


class UnihanStrokeCountBuilder(UnihanDerivedBuilder):
    """
    Builds a mapping between characters and their stroke count using the Unihan
    data.
    """
    class StrokeCountExtractor:
        """Extracts the character stroke count mapping."""
        def __init__(self, entries, quiet=False):
            """
            Initialises the StrokeCountExtractor.

            @type entries: list of tuple
            @param entries: character entries from the Unihan database
            @type quiet: bool
            @param quiet: if true no status information will be printed
            """
            self.entries = entries
            self.quiet = quiet

        def generator(self):
            """Provides one entry per radical and character."""
            for character, strokeCount in self.entries:
                yield(character, strokeCount)

    PROVIDES = 'UnihanStrokeCount'
    COLUMN_SOURCE = 'kTotalStrokes'
    COLUMN_TARGETS = ['StrokeCount']
    COLUMN_TARGETS_TYPES = {'StrokeCount': Integer()}
    PRIMARY_KEYS = ['ChineseCharacter', 'StrokeCount']
    GENERATOR_CLASS = StrokeCountExtractor


class CharacterRadicalBuilder(UnihanDerivedBuilder):
    """
    Provides an abstract class for building a character radical mapping table
    using the Unihan database.
    """
    class RadicalExtractor:
        """Generates the radical to character mapping from the Unihan table."""
        RADICAL_REGEX = re.compile(ur"(\d+)\.(\d+)")

        def __init__(self, rsEntries, quiet=False):
            """
            Initialises the RadicalExtractor.

            @type rsEntries: list of tuple
            @param rsEntries: character radical entries from the Unihan database
            @type quiet: bool
            @param quiet: if true no status information will be printed
            """
            self.rsEntries = rsEntries
            self.quiet = quiet

        def generator(self):
            """Provides one entry per radical and character."""
            for character, radicalStroke in self.rsEntries:
                matchObj = self.RADICAL_REGEX.match(radicalStroke)
                if matchObj:
                    radical = matchObj.group(1)
                    yield(character, radical)
                elif not self.quiet:
                    warn("unable to read radical information of character '" \
                        + character + "': '" + radicalStroke + "'")

    COLUMN_TARGETS = ['RadicalIndex']
    COLUMN_TARGETS_TYPES = {'RadicalIndex': Integer()}
    PRIMARY_KEYS = ['ChineseCharacter', 'RadicalIndex']
    GENERATOR_CLASS = RadicalExtractor


class CharacterKangxiRadicalBuilder(CharacterRadicalBuilder):
    """
    Builds the character Kangxi radical mapping table from the Unihan database.
    """
    PROVIDES = 'CharacterKangxiRadical'
    COLUMN_SOURCE = 'kRSKangXi'


class CharacterKanWaRadicalBuilder(CharacterRadicalBuilder):
    """
    Builds the character Dai Kan-Wa jiten radical mapping table from the Unihan
    database.
    """
    PROVIDES = 'CharacterKanWaRadical'
    COLUMN_SOURCE = 'kRSKanWa'


class CharacterJapaneseRadicalBuilder(CharacterRadicalBuilder):
    """
    Builds the character Japanese radical mapping table from the Unihan
    database.
    """
    PROVIDES = 'CharacterJapaneseRadical'
    COLUMN_SOURCE = 'kRSJapanese'


class CharacterKoreanRadicalBuilder(CharacterRadicalBuilder):
    """
    Builds the character Korean radical mapping table from the Unihan
    database.
    """
    PROVIDES = 'CharacterKoreanRadical'
    COLUMN_SOURCE = 'kRSKorean'


class CharacterVariantBuilder(EntryGeneratorBuilder):
    """
    Builds a character variant mapping table from the Unihan database. By
    default only chooses characters from the X{Basic Multilingual Plane}
    (X{BMP}) with code values between U+0000 and U+FFFF.

    Windows versions of Python by default are I{narrow build}s and don't support
    characters outside the 16 bit range. MySQL < 6 doesn't support true UTF-8,
    and uses a Version with max 3 bytes:
    U{http://dev.mysql.com/doc/refman/6.0/en/charset-unicode.html}.
    """
    class VariantGenerator:
        """Generates the character to variant mapping from the Unihan table."""

        # Regular expressions for different entry types
        HEX_INDEX_REGEX = re.compile(ur"\s*U\+([0-9A-F]+)\s*$")
        MULT_HEX_INDEX_REGEX = re.compile(ur"\s*(U\+([0-9A-F]+)( |(?=$)))+\s*$")
        MULT_HEX_INDEX_FIND_REGEX = re.compile(ur"U\+([0-9A-F]+)(?: |(?=$))")
        SEMANTIC_REGEX = re.compile(ur"(U\+[0-9A-F]+(<\S+)?( |(?=$)))+$")
        SEMANTIC_FIND_REGEX = re.compile(ur"U\+([0-9A-F]+)(?:<\S+)?(?: |(?=$))")
        ZVARIANT_REGEX = re.compile(ur"\s*U\+([0-9A-F]+)(?:\:\S+)?\s*$")

        VARIANT_REGEX_MAPPING = {'C': (HEX_INDEX_REGEX, HEX_INDEX_REGEX),
            'M': (SEMANTIC_REGEX, SEMANTIC_FIND_REGEX),
            'S': (MULT_HEX_INDEX_REGEX, MULT_HEX_INDEX_FIND_REGEX),
            'P': (SEMANTIC_REGEX, SEMANTIC_FIND_REGEX),
            'T': (MULT_HEX_INDEX_REGEX, MULT_HEX_INDEX_FIND_REGEX),
            'Z': (ZVARIANT_REGEX, ZVARIANT_REGEX)}
        """
        Mapping of entry types to regular expression describing the entry's
        pattern.
        """

        def __init__(self, variantEntries, typeList, wideBuild=False,
            quiet=False):
            """
            Initialises the VariantGenerator.

            @type variantEntries: list of tuple
            @param variantEntries: character variant entries from the Unihan
                database
            @type typeList: list of str
            @param typeList: variant types in the order given in tableEntries
            @type wideBuild: bool
            @param wideBuild: if C{True} characters outside the I{BMP} will be
                included.
            @type quiet: bool
            @param quiet: if true no status information will be printed
            """
            self.variantEntries = variantEntries
            self.typeList = typeList
            self.wideBuild = wideBuild
            self.quiet = quiet

        def generator(self):
            """Provides one entry per variant and character."""
            for entries in self.variantEntries:
                character = entries[0]
                for i, variantType in enumerate(self.typeList):
                    variantInfo = entries[i+1]
                    if variantInfo:
                        # get proper regular expression for given variant info
                        matchR, findR = self.VARIANT_REGEX_MAPPING[variantType]
                        if matchR.match(variantInfo):
                            # get all hex indices
                            variantIndices = findR.findall(variantInfo)
                            for unicodeHexIndex in variantIndices:
                                codePoint = int(unicodeHexIndex, 16)
                                if self.wideBuild \
                                    or codePoint < int('20000', 16):
                                    variant = unichr(codePoint)
                                    yield(character, variant, variantType)
                        elif not self.quiet:
                            # didn't match the regex
                            warn('unable to read variant information of ' \
                                + "character '" + character + "' for type '" \
                                + variantType + "': '" + variantInfo + "'")

    PROVIDES = 'CharacterVariant'
    DEPENDS = ['Unihan']

    COLUMN_SOURCE_ABBREV = {'kCompatibilityVariant': 'C',
        'kSemanticVariant': 'M', 'kSimplifiedVariant': 'S',
        'kSpecializedSemanticVariant': 'P', 'kTraditionalVariant': 'T',
        'kZVariant': 'Z'}
    """
    Unihan table columns providing content for the table together with their
    abbreviation used in the target table.
    """
    COLUMN_TYPES = {'ChineseCharacter': String(1), 'Variant': String(1),
        'Type': String(1)}

    COLUMNS = ['ChineseCharacter', 'Variant', 'Type']
    PRIMARY_KEYS = COLUMNS

    def __init__(self, **options):
        """
        Constructs the CharacterVariantBuilder.

        @param options: extra options
        @keyword dbConnectInst: instance of a L{DatabaseConnector}
        @keyword dataPath: optional list of paths to the data file(s)
        @keyword quiet: if C{True} no status information will be printed to
            stderr
        @keyword wideBuild: if C{True} characters outside the I{BMP} will be
            included.
        """
        # constructor is only defined for docstring
        super(CharacterVariantBuilder, self).__init__(**options)

    @classmethod
    def getDefaultOptions(cls):
        options = super(CharacterVariantBuilder, cls).getDefaultOptions()
        options.update({'wideBuild': False})

        return options

    @classmethod
    def getOptionMetaData(cls, option):
        optionsMetaData = {'wideBuild': {'type': 'bool',
                'description': "include characters outside the Unicode BMP"}}

        if option in optionsMetaData:
            return optionsMetaData[option]
        else:
            return super(CharacterVariantBuilder, cls).getOptionMetaData(option)

    def getGenerator(self):
        # create generator
        keys = self.COLUMN_SOURCE_ABBREV.keys()
        variantTypes = [self.COLUMN_SOURCE_ABBREV[key] for key in keys]
        selectKeys = ['ChineseCharacter']
        selectKeys.extend(keys)

        table = self.db.tables['Unihan']
        tableEntries = self.db.selectRows(
            select([table.c[column] for column in selectKeys]))
        return CharacterVariantBuilder.VariantGenerator(tableEntries,
            variantTypes, wideBuild=self.wideBuild, quiet=self.quiet)\
                .generator()

    def build(self):
        if not self.quiet:
            warn("Reading table content from Unihan columns '%s'"
                % "', '".join(self.COLUMN_SOURCE_ABBREV.keys()))
        super(CharacterVariantBuilder, self).build()


class UnihanCharacterSetBuilder(EntryGeneratorBuilder):
    """
    Builds a simple list of characters that belong to a specific class using the
    Unihan data.
    """
    DEPENDS = ['Unihan']

    COLUMNS = ['ChineseCharacter']
    PRIMARY_KEYS = COLUMNS
    COLUMN_TYPES = {'ChineseCharacter': String(1)}

    def getGenerator(self):
        # create generator
        table = self.db.tables['Unihan']
        # read rows here instead of scalars to yield tuples for the generator
        tableEntries = self.db.selectRows(
            select([table.c.ChineseCharacter],
                table.c[self.COLUMN_SOURCE] != None))
        return ListGenerator(tableEntries).generator()

    def build(self):
        if not self.quiet:
            warn("Reading table content from Unihan column '%s'"
                % self.COLUMN_SOURCE)
        super(UnihanCharacterSetBuilder, self).build()


class IICoreSetBuilder(UnihanCharacterSetBuilder):
    u"""
    Builds a simple list of all characters in X{IICore}
    (Unicode I{International Ideograph Core)}.
    @see: Chinese Wikipedia on IICore:
        U{http://zh.wikipedia.org/wiki/國際表意文字核心}
    """
    PROVIDES = 'IICoreSet'
    COLUMN_SOURCE = 'kIICore'


class GB2312SetBuilder(UnihanCharacterSetBuilder):
    """
    Builds a simple list of all characters in the Chinese standard X{GB2312-80}.
    """
    PROVIDES = 'GB2312Set'
    COLUMN_SOURCE = 'kGB0'


class BIG5SetBuilder(UnihanCharacterSetBuilder):
    """
    Builds a simple list of all characters in the Chinese standard X{BIG5}.
    """
    PROVIDES = 'BIG5Set'
    COLUMN_SOURCE = 'kBigFive'

#}
#{ Unihan reading information

class CharacterReadingBuilder(UnihanDerivedBuilder):
    """
    Provides an abstract class for building a character reading mapping table
    using the Unihan database.
    """
    class SimpleReadingSplitter:
        """Generates the reading entities from the Unihan table."""
        SPLIT_REGEX = re.compile(r"(\S+)")

        def __init__(self, readingEntries, quiet=False):
            """
            Initialises the ReadingSplitter.

            @type readingEntries: list of tuple
            @param readingEntries: character reading entries from the Unihan
                database
            @type quiet: bool
            @param quiet: if true no status information will be printed
            """
            self.readingEntries = readingEntries
            self.quiet = quiet

        def generator(self):
            """Provides one entry per reading entity and character."""
            for character, readings in self.readingEntries:
                readingList = self.SPLIT_REGEX.findall(readings)
                if not self.quiet and len(set(readingList)) < len(readingList):
                    warn('reading information of character ' + character \
                        + ' is inconsistent: ' + ', '.join(readingList))
                for reading in set(readingList):
                    yield(character, reading.lower())

    COLUMN_TARGETS = ['Reading']
    COLUMN_TARGETS_TYPES = {'Reading': String(255)}
    PRIMARY_KEYS = ['ChineseCharacter', 'Reading']
    GENERATOR_CLASS = SimpleReadingSplitter


class CharacterUnihanPinyinBuilder(CharacterReadingBuilder):
    """
    Builds the character Pinyin mapping table from the Unihan database.
    """
    PROVIDES = 'CharacterUnihanPinyin'
    COLUMN_SOURCE = 'kMandarin'


class CharacterJyutpingBuilder(CharacterReadingBuilder):
    """Builds the character Jyutping mapping table from the Unihan database."""
    PROVIDES = 'CharacterJyutping'
    COLUMN_SOURCE = 'kCantonese'


class CharacterJapaneseKunBuilder(CharacterReadingBuilder):
    """Builds the character Kun'yomi mapping table from the Unihan database."""
    PROVIDES = 'CharacterJapaneseKun'
    COLUMN_SOURCE = 'kJapaneseKun'


class CharacterJapaneseOnBuilder(CharacterReadingBuilder):
    """Builds the character On'yomi mapping table from the Unihan database."""
    PROVIDES = 'CharacterJapaneseOn'
    COLUMN_SOURCE = 'kJapaneseOn'


class CharacterHangulBuilder(CharacterReadingBuilder):
    """Builds the character Hangul mapping table from the Unihan database."""
    PROVIDES = 'CharacterHangul'
    COLUMN_SOURCE = 'kHangul'


class CharacterVietnameseBuilder(CharacterReadingBuilder):
    """
    Builds the character Vietnamese mapping table from the Unihan database.
    """
    PROVIDES = 'CharacterVietnamese'
    COLUMN_SOURCE = 'kVietnamese'


class CharacterXHPCReadingBuilder(UnihanDerivedBuilder):
    """
    Builds the Xiandai Hanyu Pinlu Cidian Pinyin mapping table using the Unihan
    database.
    """
    class XHPCReadingSplitter():
        """
        Generates the Xiandai Hanyu Pinlu Cidian Pinyin syllables from the
        Unihan table.
        """
        SPLIT_REGEX = re.compile(ur"([a-zü]+[1-5])\(([0-9]+)\)")

        def __init__(self, readingEntries, quiet=False):
            """
            Initialises the XHPCReadingSplitter.

            @type readingEntries: list of tuple
            @param readingEntries: character reading entries from the Unihan
                database
            @type quiet: bool
            @param quiet: if true no status information will be printed
            """
            self.readingEntries = readingEntries
            self.quiet = quiet

        def generator(self):
            """Provides one entry per reading entity and character."""
            for character, readings in self.readingEntries:
                readingList = self.SPLIT_REGEX.findall(readings)
                readingDict = dict(readingList)
                if not self.quiet and len(readingDict) < len(readingList):
                    warn('reading information of character ' + character \
                        + ' is inconsistent: ' + ', '.join(readingList))
                for reading, frequency in readingDict.items():
                    yield(character, reading.lower(), frequency)

    PROVIDES = 'CharacterXHPCPinyin'
    COLUMN_SOURCE = 'kHanyuPinlu'
    COLUMN_TARGETS = ['Reading', 'Frequency']
    COLUMN_TARGETS_TYPES = {'Reading': String(255), 'Frequency': Integer()}
    PRIMARY_KEYS = ['ChineseCharacter', 'Reading']
    GENERATOR_CLASS = XHPCReadingSplitter


class CharacterDiacriticPinyinBuilder(CharacterReadingBuilder):
    """
    Builds Pinyin mapping table using the Unihan database for syllables with
    diacritics.
    """
    class ReadingSplitter:
        """
        Generates Pinyin syllables from Unihan entries in diacritic form.
        """
        SPLIT_REGEX = re.compile(r"[0-9,.*]+:(\S+)")

        TONEMARK_VOWELS = [u'a', u'e', u'i', u'o', u'u', u'ü', u'n', u'm', u'r',
            u'ê']

        TONEMARK_MAP = {u'\u0304': 1, u'\u0301': 2, u'\u030c': 3, u'\u0300': 4}

        def __init__(self, readingEntries, quiet=False):
            """
            Initialises the ReadingSplitter.

            @type readingEntries: list of tuple
            @param readingEntries: character reading entries from the Unihan
                database
            @type quiet: bool
            @param quiet: if true no status information will be printed
            """
            self.readingEntries = readingEntries
            self.quiet = quiet
            self._toneMarkRegex = re.compile(u'[' \
                + ''.join(self.TONEMARK_MAP.keys()) + ']')

        def convertTonemark(self, entity):
            """
            Converts the entity with diacritics into an entity with tone mark
            as appended number.

            @type entity: str
            @param entity: entity with tonal information
            @rtype: tuple
            @return: plain entity without tone mark and entity's tone index
                (starting with 1)
            """
            import unicodedata
            # get decomposed Unicode string, e.g. C{'ū'} to C{'u\u0304'}
            entity = unicodedata.normalize("NFD", unicode(entity))
            # find character with tone marker
            matchObj = self._toneMarkRegex.search(entity)
            if matchObj:
                diacriticalMark = matchObj.group(0)
                tone = self.TONEMARK_MAP[diacriticalMark]
                # strip off diacritical mark
                plainEntity = entity.replace(diacriticalMark, '')
                # compose Unicode string (used for ê) and return with tone
                return unicodedata.normalize("NFC", plainEntity) + str(tone)
            else:
                # fifth tone doesn't have any marker
                return unicodedata.normalize("NFC", entity) + '5'

        def generator(self):
            """Provides one entry per reading entity and character."""
            for character, readings in self.readingEntries:
                readingList = self.SPLIT_REGEX.findall(readings)
                if not self.quiet and len(set(readingList)) < len(readingList):
                    warn('reading information of character ' + character \
                        + ' is inconsistent: ' + ', '.join(readingList))
                readings = set()
                for readingEntry in set(readingList):
                    readings.update(readingEntry.split(','))
                for reading in readings:
                    yield(character, self.convertTonemark(reading.lower()))

    GENERATOR_CLASS = ReadingSplitter


class CharacterXHCReadingBuilder(CharacterDiacriticPinyinBuilder):
    """
    Builds the Xiandai Hanyu Cidian Pinyin mapping table using the Unihan
    database.
    """
    PROVIDES = 'CharacterXHCPinyin'
    COLUMN_SOURCE = 'kXHC1983'


class CharacterHDZReadingBuilder(CharacterDiacriticPinyinBuilder):
    """
    Builds the Hanyu Da Zidian Pinyin mapping table using the Unihan database.
    """
    PROVIDES = 'CharacterHDZPinyin'
    COLUMN_SOURCE = 'kHanyuPinyin'


class CharacterPinyinAdditionalBuilder(EntryGeneratorBuilder):
    """
    Provides a mapping of character to Pinyin with additional data not found
    in other sources.
    """
    PROVIDES = 'CharacterAdditionalPinyin'
    COLUMNS = ['ChineseCharacter', 'Reading']
    PRIMARY_KEYS = COLUMNS
    COLUMN_TYPES = {'ChineseCharacter': String(1), 'Reading': String(255)}

    def getGenerator(self):
        tableEntries = [
            (u'〇', 'ling2'), # as mentioned in kHanyuPinlu, kXHC1983
            ]
        return ListGenerator(tableEntries).generator()


class CharacterPinyinBuilder(EntryGeneratorBuilder):
    """
    Builds the character Pinyin mapping table from the several sources.
    """
    PROVIDES = 'CharacterPinyin'
    DEPENDS = ['CharacterUnihanPinyin', 'CharacterXHPCPinyin',
        'CharacterXHCPinyin', 'CharacterHDZPinyin', 'CharacterAdditionalPinyin']

    COLUMNS = ['ChineseCharacter', 'Reading']
    PRIMARY_KEYS = COLUMNS
    COLUMN_TYPES = {'ChineseCharacter': String(1), 'Reading': String(255)}

    def getGenerator(self):
        # create generator
        selectQueries = []
        for tableName in self.DEPENDS:
            table = self.db.tables[tableName]
            selectQueries.append(
                select([table.c[column] for column in self.COLUMNS]))

        tableEntries = self.db.selectRows(union(*selectQueries))
        return ListGenerator(tableEntries).generator()

#}
#{ CSV file based

class CSVFileLoader(TableBuilder):
    """
    Builds a table by loading its data from a list of comma separated values
    (CSV).
    """
    TABLE_CSV_FILE_MAPPING = ''
    """csv file path"""
    TABLE_DECLARATION_FILE_MAPPING = ''
    """file path containing SQL create table code."""
    INDEX_KEYS = []
    """Index keys (not unique) of the created table"""

    class DefaultDialect(csv.Dialect):
        """Defines a default dialect for the case sniffing fails."""
        quoting = csv.QUOTE_NONE
        delimiter = ','
        lineterminator = '\n'
        quotechar = "'"

    # TODO unicode_csv_reader(), utf_8_encoder(), byte_string_dialect() used
    #  to work around missing Unicode support in csv module
    @staticmethod
    def unicode_csv_reader(unicode_csv_data, dialect, **kwargs):
        # csv.py doesn't do Unicode; encode temporarily as UTF-8:
        csv_reader = csv.reader(CSVFileLoader.utf_8_encoder(unicode_csv_data),
            dialect=CSVFileLoader.byte_string_dialect(dialect), **kwargs)
        for row in csv_reader:
            # decode UTF-8 back to Unicode, cell by cell:
            yield [unicode(cell, 'utf-8') for cell in row]

    @staticmethod
    def utf_8_encoder(unicode_csv_data):
        for line in unicode_csv_data:
            yield line.encode('utf-8')

    @staticmethod
    def byte_string_dialect(dialect):
        class ByteStringDialect(csv.Dialect):
            def __init__(self, dialect):
                for attr in ["delimiter", "quotechar", "escapechar", "lineterminator"]:
                    old = getattr(dialect, attr)
                    if old is not None:
                        setattr(self, attr, str(old))

                for attr in ["doublequote", "skipinitialspace", "quoting"]:
                    setattr(self, attr, getattr(dialect, attr))

                csv.Dialect.__init__(self)

        return ByteStringDialect(dialect)

    def getCSVReader(self, fileHandle):
        """
        Returns a csv reader object for a given file name.

        The file can start with the character '#' to mark comments. These will
        be ignored. The first line after the leading comments will be used to
        guess the csv file's format.

        @type fileHandle: file
        @param fileHandle: file handle of the CSV file
        @rtype: instance
        @return: CSV reader object returning one entry per line
        """
        def prependLineGenerator(line, data):
            """
            The first line red for guessing format has to be reinserted.
            """
            yield line
            for nextLine in data:
                yield nextLine

        line = '#'
        try:
            while line.strip().startswith('#'):
                line = fileHandle.next()
        except StopIteration:
            return csv.reader(fileHandle)
        try:
            self.fileDialect = csv.Sniffer().sniff(line, ['\t', ','])
        except csv.Error:
            self.fileDialect = CSVFileLoader.DefaultDialect()

        content = prependLineGenerator(line, fileHandle)
        #return csv.reader(content, dialect=self.fileDialect) # TODO
        return CSVFileLoader.unicode_csv_reader(content, self.fileDialect)

    def build(self):
        import codecs

        definitionFile = self.findFile([self.TABLE_DECLARATION_FILE_MAPPING],
            "SQL table definition file")
        contentFile = self.findFile([self.TABLE_CSV_FILE_MAPPING], "table")

        # get create statement
        if not self.quiet:
            warn("Reading table definition from file '" + definitionFile + "'")

        fileHandle = codecs.open(definitionFile, 'r', 'utf-8')
        createStatement = ''.join(fileHandle.readlines()).strip("\n")
        # get create statement
        self.db.execute(text(createStatement))
        table = Table(self.PROVIDES, self.db.metadata, autoload=True)

        # write table content
        if not self.quiet:
            warn("Reading table '" + self.PROVIDES + "' from file '" \
                + contentFile + "'")
        fileHandle = codecs.open(contentFile, 'r', 'utf-8')

        entries = []
        for line in self.getCSVReader(fileHandle):
            if len(line) == 1 and not line[0].strip():
                continue
            entryDict = dict([(column.name, line[i]) \
                for i, column in enumerate(table.columns)])
            entries.append(entryDict)

        try:
            self.db.execute(table.insert(), entries)
        except IntegrityError, e:
            if not self.quiet:
                warn(unicode(e))
                #warn(unicode(insertStatement))
            raise

        # get create index statement
        for index in self.buildIndexObjects(self.PROVIDES, self.INDEX_KEYS):
            index.create()


class PinyinSyllablesBuilder(CSVFileLoader):
    """
    Builds a list of Pinyin syllables.
    """
    PROVIDES = 'PinyinSyllables'

    TABLE_CSV_FILE_MAPPING = 'pinyinsyllables.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'pinyinsyllables.sql'


class PinyinInitialFinalBuilder(CSVFileLoader):
    """
    Builds a mapping from Pinyin syllables to their initial/final parts.
    """
    PROVIDES = 'PinyinInitialFinal'

    TABLE_CSV_FILE_MAPPING = 'pinyininitialfinal.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'pinyininitialfinal.sql'


class WadeGilesSyllablesBuilder(CSVFileLoader):
    """
    Builds a list of Wade-Giles syllables.
    """
    PROVIDES = 'WadeGilesSyllables'

    TABLE_CSV_FILE_MAPPING = 'wadegilessyllables.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'wadegilessyllables.sql'


class WadeGilesInitialFinalBuilder(CSVFileLoader):
    """
    Builds a mapping from Wade-Giles syllables to their initial/final parts.
    """
    PROVIDES = 'WadeGilesInitialFinal'

    TABLE_CSV_FILE_MAPPING = 'wadegilesinitialfinal.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'wadegilesinitialfinal.sql'


class GRSyllablesBuilder(CSVFileLoader):
    """
    Builds a list of Gwoyeu Romatzyh syllables.
    """
    PROVIDES = 'GRSyllables'

    TABLE_CSV_FILE_MAPPING = 'grsyllables.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'grsyllables.sql'


class GRRhotacisedFinalsBuilder(CSVFileLoader):
    """
    Builds a list of Gwoyeu Romatzyh rhotacised finals.
    """
    PROVIDES = 'GRRhotacisedFinals'

    TABLE_CSV_FILE_MAPPING = 'grrhotacisedfinals.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'grrhotacisedfinals.sql'


class GRAbbreviationBuilder(CSVFileLoader):
    """
    Builds a list of Gwoyeu Romatzyh abbreviated spellings.
    """
    PROVIDES = 'GRAbbreviation'

    TABLE_CSV_FILE_MAPPING = 'grabbreviation.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'grabbreviation.sql'


class JyutpingSyllablesBuilder(CSVFileLoader):
    """
    Builds a list of Jyutping syllables.
    """
    PROVIDES = 'JyutpingSyllables'

    TABLE_CSV_FILE_MAPPING = 'jyutpingsyllables.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'jyutpingsyllables.sql'


class JyutpingInitialFinalBuilder(CSVFileLoader):
    """
    Builds a mapping from Jyutping syllables to their initial/final parts.
    """
    PROVIDES = 'JyutpingInitialFinal'

    TABLE_CSV_FILE_MAPPING = 'jyutpinginitialfinal.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'jyutpinginitialfinal.sql'


class CantoneseYaleSyllablesBuilder(CSVFileLoader):
    """
    Builds a list of Cantonese Yale syllables.
    """
    PROVIDES = 'CantoneseYaleSyllables'

    TABLE_CSV_FILE_MAPPING = 'cantoneseyalesyllables.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'cantoneseyalesyllables.sql'


class CantoneseYaleInitialNucleusCodaBuilder(CSVFileLoader):
    """
    Builds a mapping of Cantonese syllable in the Yale romanisation
    system to the syllables' initial, nucleus and coda.
    """
    PROVIDES = 'CantoneseYaleInitialNucleusCoda'

    TABLE_CSV_FILE_MAPPING = 'cantoneseyaleinitialnucleuscoda.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'cantoneseyaleinitialnucleuscoda.sql'


class JyutpingYaleMappingBuilder(CSVFileLoader):
    """
    Builds a mapping between syllables in Jyutping and the Yale romanization
    system.
    """
    PROVIDES = 'JyutpingYaleMapping'

    TABLE_CSV_FILE_MAPPING = 'jyutpingyalemapping.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'jyutpingyalemapping.sql'


class WadeGilesPinyinMappingBuilder(CSVFileLoader):
    """
    Builds a mapping between syllables in Wade-Giles and Pinyin.
    """
    PROVIDES = 'WadeGilesPinyinMapping'

    TABLE_CSV_FILE_MAPPING = 'wadegilespinyinmapping.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'wadegilespinyinmapping.sql'


class PinyinGRMappingBuilder(CSVFileLoader):
    """
    Builds a mapping between syllables in Pinyin and Gwoyeu Romatzyh.
    """
    PROVIDES = 'PinyinGRMapping'

    TABLE_CSV_FILE_MAPPING = 'pinyingrmapping.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'pinyingrmapping.sql'


class PinyinIPAMappingBuilder(CSVFileLoader):
    """
    Builds a mapping between syllables in Pinyin and their representation in
    IPA.
    """
    PROVIDES = 'PinyinIPAMapping'

    TABLE_CSV_FILE_MAPPING = 'pinyinipamapping.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'pinyinipamapping.sql'


class MandarinIPAInitialFinalBuilder(CSVFileLoader):
    """
    Builds a mapping from Mandarin syllables in IPA to their initial/final
    parts.
    """
    PROVIDES = 'MandarinIPAInitialFinal'

    TABLE_CSV_FILE_MAPPING = 'mandarinipainitialfinal.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'mandarinipainitialfinal.sql'


class JyutpingIPAMappingBuilder(CSVFileLoader):
    """
    Builds a mapping between syllables in Jyutping and their representation in
    IPA.
    """
    PROVIDES = 'JyutpingIPAMapping'

    TABLE_CSV_FILE_MAPPING = 'jyutpingipamapping.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'jyutpingipamapping.sql'


class CantoneseIPAInitialFinalBuilder(CSVFileLoader):
    """
    Builds a mapping from Cantonese syllables in IPA to their initial/final
    parts.
    """
    PROVIDES = 'CantoneseIPAInitialFinal'

    TABLE_CSV_FILE_MAPPING = 'cantoneseipainitialfinal.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'cantoneseipainitialfinal.sql'


class KangxiRadicalBuilder(CSVFileLoader):
    """
    Builds a mapping between Kangxi radical index and radical characters.
    """
    PROVIDES = 'KangxiRadical'

    TABLE_CSV_FILE_MAPPING = 'kangxiradical.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'kangxiradical.sql'


class KangxiRadicalIsolatedCharacterBuilder(CSVFileLoader):
    """
    Builds a mapping between Kangxi radical index and radical equivalent
    characters without radical form.
    """
    PROVIDES = 'KangxiRadicalIsolatedCharacter'

    TABLE_CSV_FILE_MAPPING = 'kangxiradicalisolatedcharacter.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'kangxiradicalisolatedcharacter.sql'


class RadicalEquivalentCharacterBuilder(CSVFileLoader):
    """
    Builds a mapping between I{Unicode radical forms} and
    I{Unicode radical variants} on one side and I{equivalent characters} on the
    other side.
    """
    PROVIDES = 'RadicalEquivalentCharacter'

    TABLE_CSV_FILE_MAPPING = 'radicalequivalentcharacter.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'radicalequivalentcharacter.sql'


class StrokesBuilder(CSVFileLoader):
    """
    Builds a list of strokes and their names.
    """
    PROVIDES = 'Strokes'

    TABLE_CSV_FILE_MAPPING = 'strokes.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'strokes.sql'


class StrokeOrderBuilder(CSVFileLoader):
    """
    Builds a mapping between characters and their stroke order.
    """
    PROVIDES = 'StrokeOrder'

    TABLE_CSV_FILE_MAPPING = 'strokeorder.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'strokeorder.sql'


class CharacterDecompositionBuilder(CSVFileLoader):
    """
    Builds a mapping between characters and their decomposition.
    """
    PROVIDES = 'CharacterDecomposition'

    TABLE_CSV_FILE_MAPPING = 'characterdecomposition.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'characterdecomposition.sql'
    INDEX_KEYS = [['ChineseCharacter', 'ZVariant']]


class LocaleCharacterVariantBuilder(CSVFileLoader):
    """
    Builds a mapping between a character under a locale and its default variant.
    """
    PROVIDES = 'LocaleCharacterVariant'

    TABLE_CSV_FILE_MAPPING = 'localecharactervariant.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'localecharactervariant.sql'


class MandarinBraileInitialBuilder(CSVFileLoader):
    """
    Builds a mapping of Mandarin Chinese syllable initials in Pinyin to Braille
    characters.
    """
    PROVIDES = 'PinyinBrailleInitialMapping'

    TABLE_CSV_FILE_MAPPING = 'pinyinbrailleinitialmapping.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'pinyinbrailleinitialmapping.sql'


class MandarinBraileFinalBuilder(CSVFileLoader):
    """
    Builds a mapping of Mandarin Chinese syllable finals in Pinyin to Braille
    characters.
    """
    PROVIDES = 'PinyinBrailleFinalMapping'

    TABLE_CSV_FILE_MAPPING = 'pinyinbraillefinalmapping.csv'
    TABLE_DECLARATION_FILE_MAPPING = 'pinyinbraillefinalmapping.sql'


#}
#{ Library dependant

class ZVariantBuilder(EntryGeneratorBuilder):
    """
    Builds a list of glyph indices for characters.
    @todo Impl: Check if all Z-variants in LocaleCharacterVariant are included.
    """
    PROVIDES = 'ZVariants'
    DEPENDS = ['CharacterDecomposition', 'StrokeOrder', 'Unihan']
    # TODO 'LocaleCharacterVariant'

    COLUMNS = ['ChineseCharacter', 'ZVariant']
    PRIMARY_KEYS = ['ChineseCharacter', 'ZVariant']
    INDEX_KEYS = [['ChineseCharacter']]
    COLUMN_TYPES = {'ChineseCharacter': String(1), 'ZVariant': Integer()}

    def getGenerator(self):
        decompositionTable = self.db.tables['CharacterDecomposition']
        strokeOrderTable = self.db.tables['StrokeOrder']
        unihanTable = self.db.tables['Unihan']

        characterSet = set(self.db.selectRows(
            select([decompositionTable.c.ChineseCharacter,
                decompositionTable.c.ZVariant], distinct=True)))
        characterSet.update(self.db.selectRows(
            select([strokeOrderTable.c.ChineseCharacter,
                strokeOrderTable.c.ZVariant])))
        # TODO
        #characterSet.update(self.db.select('LocaleCharacterVariant',
            #['ChineseCharacter', 'ZVariant']))
        # Add characters from Unihan as Z-variant 0
        unihanCharacters = self.db.selectScalars(
            select([unihanTable.c.ChineseCharacter],
                or_(unihanTable.c.kTotalStrokes != None,
                    unihanTable.c.kRSKangXi != None)))
        characterSet.update([(char, 0) for char in unihanCharacters])

        return ListGenerator(characterSet).generator()


class StrokeCountBuilder(EntryGeneratorBuilder):
    """
    Builds a mapping between characters and their stroke count.
    """
    class StrokeCountGenerator:
        """Generates the character stroke count mapping."""
        def __init__(self, dbConnectInst, characterSet, quiet=False):
            """
            Initialises the StrokeCountGenerator.

            @type dbConnectInst: instance
            @param dbConnectInst: instance of a L{DatabaseConnector}.
            @type characterSet: set
            @param characterSet: set of characters to generate the table for
            @type quiet: bool
            @param quiet: if true no status information will be printed to
                stderr
            """
            self.characterSet = characterSet
            self.quiet = quiet
            # create instance, locale is not important, we supply own zVariant
            self.cjk = characterlookup.CharacterLookup('T',
                dbConnectInst=dbConnectInst)
            # make sure a currently existing table is not used
            self.cjk.hasStrokeCount = False

        def generator(self):
            """Provides one entry per character, z-Variant and locale subset."""
            for char, zVariant in self.characterSet:
                try:
                    # cjklib's stroke count method uses the stroke order
                    #   information as long as this table doesn't exist
                    strokeCount = self.cjk.getStrokeCount(char,
                        zVariant=zVariant)
                    yield {'ChineseCharacter': char, 'StrokeCount': strokeCount,
                        'ZVariant': zVariant}
                except exception.NoInformationError:
                    pass
                except IndexError:
                    if not self.quiet:
                        warn("malformed IDS for character '" + char \
                            + "'")

    PROVIDES = 'StrokeCount'
    DEPENDS = ['CharacterDecomposition', 'StrokeOrder', 'Strokes']

    COLUMNS = ['ChineseCharacter', 'StrokeCount', 'ZVariant']
    PRIMARY_KEYS = ['ChineseCharacter', 'ZVariant']
    COLUMN_TYPES = {'ChineseCharacter': String(1), 'StrokeCount': Integer(),
        'ZVariant': Integer()}

    def getGenerator(self):
        decompositionTable = self.db.tables['CharacterDecomposition']
        strokeOrderTable = self.db.tables['StrokeOrder']

        characterSet = set(self.db.selectRows(
            select([decompositionTable.c.ChineseCharacter,
                decompositionTable.c.ZVariant], distinct=True)))
        characterSet.update(self.db.selectRows(
            select([strokeOrderTable.c.ChineseCharacter,
                strokeOrderTable.c.ZVariant])))
        return StrokeCountBuilder.StrokeCountGenerator(self.db, characterSet,
            self.quiet).generator()


class CombinedStrokeCountBuilder(StrokeCountBuilder):
    """
    Builds a mapping between characters and their stroke count. Includes stroke
    count data from the Unihan database to make up for missing data in own data
    files.
    """
    class CombinedStrokeCountGenerator:
        """Generates the character stroke count mapping."""
        def __init__(self, dbConnectInst, characterSet, tableEntries,
            preferredBuilder, quiet=False):
            """
            Initialises the CombinedStrokeCountGenerator.

            @type dbConnectInst: instance
            @param dbConnectInst: instance of a L{DatabaseConnector}.
            @type characterSet: set
            @param characterSet: set of characters to generate the table for
            @type tableEntries: list of list
            @param tableEntries: list of characters with Z-variant
            @type preferredBuilder: instance
            @param preferredBuilder: TableBuilder which forms are preferred over
                entries from the Unihan table
            @type quiet: bool
            @param quiet: if true no status information will be printed to
                stderr
            """
            self.characterSet = characterSet
            self.tableEntries = tableEntries
            self.preferredBuilder = preferredBuilder
            self.quiet = quiet
            # create instance, locale is not important, we supply own zVariant
            self.cjk = characterlookup.CharacterLookup('T',
                dbConnectInst=dbConnectInst)
            self.db = dbConnectInst

        def getStrokeCount(self, char, zVariant, strokeCountDict,
            unihanStrokeCountDict, decompositionDict):
            """
            Gets the stroke count of the given character by summing up the
            stroke count of its components and using the Unihan table as
            fallback.

            For the sake of consistency this method doesn't take the stroke
            count given by Unihan directly but sums up the stroke counts of the
            components to make sure the sum of component's stroke count will
            always give the characters stroke count. The result yielded will be
            in many cases even more precise than the value given in Unihan (not
            depending on the actual glyph form).

            Once calculated the stroke count will be cached in the given
            strokeCountDict object.

            @type char: str
            @param char: Chinese character
            @type zVariant: int
            @param zVariant: Z-variant of character
            @rtype: int
            @return: stroke count
            @raise ValueError: if stroke count is ambiguous due to inconsistent
                values wrt Unihan vs. own data.
            @raise NoInformationError: if decomposition is incomplete
            """
            if char == u'？':
                # we have an incomplete decomposition, can't build
                raise exception.NoInformationError("incomplete decomposition")

            if (char, zVariant) not in strokeCountDict:
                lastStrokeCount = None
                if (char, zVariant) in decompositionDict:
                    # try all decompositions of this character, all need to
                    #   return the same count for sake of consistency
                    for decomposition in decompositionDict[(char, zVariant)]:
                        try:
                            accumulatedStrokeCount = 0

                            for entry in decomposition:
                                if type(entry) == types.TupleType:
                                    component, componentZVariant = entry

                                    accumulatedStrokeCount += \
                                        self.getStrokeCount(component,
                                            componentZVariant, strokeCountDict,
                                            unihanStrokeCountDict,
                                            decompositionDict)

                            if lastStrokeCount != None \
                                and lastStrokeCount != accumulatedStrokeCount:
                                # different stroke counts taken from different
                                #   decompositions, can't build at all
                                raise ValueError("ambiguous stroke count " \
                                    + "information, due to various stroke " \
                                    + "count sources for " \
                                    + repr((char, zVariant)))
                            else:
                                # first run or equal to previous calculation
                                lastStrokeCount = accumulatedStrokeCount

                        except exception.NoInformationError:
                            continue

                if lastStrokeCount != None:
                    strokeCountDict[(char, zVariant)] = lastStrokeCount
                else:
                    # couldn't get stroke counts from components, check fallback
                    #   resources
                    if (char, 0) in strokeCountDict:
                        # own sources have info for fallback zVariant
                        strokeCountDict[(char, zVariant)] \
                            = strokeCountDict[(char, 0)]

                    elif char in unihanStrokeCountDict:
                        # take Unihan info
                        strokeCountDict[(char, zVariant)] \
                            = unihanStrokeCountDict[char]

                    else:
                        strokeCountDict[(char, zVariant)] = None

            if strokeCountDict[(char, zVariant)] == None:
                raise exception.NoInformationError(
                    "missing stroke count information")
            else:
                return strokeCountDict[(char, zVariant)]

        def generator(self):
            """Provides one entry per character, z-Variant and locale subset."""
            # handle chars from own data first
            strokeCountDict = {}
            for entry in self.preferredBuilder:
                yield entry

                # save stroke count for later processing, prefer Z-variant 0
                key = (entry['ChineseCharacter'], entry['ZVariant'])
                strokeCountDict[key] = entry['StrokeCount']

            # now get stroke counts from Unihan table

            # get Unihan table stroke count data
            unihanStrokeCountDict = {}
            for char, strokeCount in self.tableEntries:
                if (char, 0) not in strokeCountDict:
                    unihanStrokeCountDict[char] = strokeCount

            # finally fill up with characters from Unihan; proper glyph
            #   information missing though in some cases.

            # remove glyphs we already have an entry for
            self.characterSet.difference_update(strokeCountDict.keys())

            # get character decompositions
            decompositionDict = self.cjk.getDecompositionEntriesDict()

            for char, zVariant in self.characterSet:
                warningZVariants = []
                try:
                    # build stroke count from mixed source
                    strokeCount = self.getStrokeCount(char, zVariant,
                        strokeCountDict, unihanStrokeCountDict,
                        decompositionDict)

                    yield {'ChineseCharacter': char, 'ZVariant': zVariant,
                        'StrokeCount': strokeCount}
                except ValueError:
                    warningZVariants.append(zVariant)
                except exception.NoInformationError:
                    pass

                if not self.quiet and warningZVariants:
                    warn("ambiguous stroke count information (mixed sources) " \
                        "for character '" + char + "' for Z-variant(s) '" \
                        + ''.join([str(z) for z in warningZVariants]) + "'")

    DEPENDS = ['CharacterDecomposition', 'StrokeOrder', 'Strokes', 'Unihan']
    COLUMN_SOURCE = 'kTotalStrokes'

    def getGenerator(self):
        decompositionTable = self.db.tables['CharacterDecomposition']
        strokeOrderTable = self.db.tables['StrokeOrder']
        unihanTable = self.db.tables['Unihan']

        characterSet = set(self.db.selectRows(
            select([decompositionTable.c.ChineseCharacter,
                decompositionTable.c.ZVariant], distinct=True)))
        characterSet.update(self.db.selectRows(
            select([strokeOrderTable.c.ChineseCharacter,
                strokeOrderTable.c.ZVariant])))
        preferredBuilder = \
            CombinedStrokeCountBuilder.StrokeCountGenerator(self.db,
                characterSet, self.quiet).generator()
        # get main builder
        tableEntries = self.db.selectRows(
            select([unihanTable.c.ChineseCharacter,
                unihanTable.c[self.COLUMN_SOURCE]],
                unihanTable.c[self.COLUMN_SOURCE] != None))

        # get characters to build combined stroke count for. Some characters
        #   from the CharacterDecomposition table might not have a stroke count
        #   entry in Unihan though their components do have.
        characterSet.update([(char, 0) for char, _ in tableEntries])

        return CombinedStrokeCountBuilder.CombinedStrokeCountGenerator(self.db,
            characterSet, tableEntries, preferredBuilder, self.quiet)\
            .generator()


class CharacterComponentLookupBuilder(EntryGeneratorBuilder):
    """
    Builds a mapping between characters and their components.
    """
    class CharacterComponentGenerator:
        """Generates the component to character mapping."""

        def __init__(self, dbConnectInst, characterSet):
            """
            Initialises the CharacterComponentGenerator.

            @type dbConnectInst: instance
            @param dbConnectInst: instance of a L{DatabaseConnector}
            @type characterSet: set
            @param characterSet: set of characters to generate the table for
            """
            self.characterSet = characterSet
            # create instance, locale is not important, we supply own zVariant
            self.cjk = characterlookup.CharacterLookup('T',
                dbConnectInst=dbConnectInst)

        def getComponents(self, char, zVariant, decompositionDict,
            componentDict):
            """
            Gets all character components for the given glyph.

            @type char: str
            @param char: Chinese character
            @type zVariant: int
            @param zVariant: Z-variant of character
            @rtype: set
            @return: all components of the character
            """
            if (char, zVariant) not in componentDict:
                componentDict[(char, zVariant)] = set()

                if (char, zVariant) in decompositionDict:
                    for decomposition in decompositionDict[(char, zVariant)]:
                        componentDict[(char, zVariant)].update(
                            [entry for entry in decomposition \
                                if type(entry) == types.TupleType])

            componentSet = set()
            for component, componentZVariant in componentDict[(char, zVariant)]:
                componentSet.add((component, componentZVariant))
                # get sub-components
                componentSet.update(self.getComponents(component,
                    componentZVariant, decompositionDict, componentDict))

            return componentSet

        def generator(self):
            """Provides the component entries."""
            decompositionDict = self.cjk.getDecompositionEntriesDict()
            componentDict = {}
            for char, zVariant in self.characterSet:
                for component, componentZVariant \
                    in self.getComponents(char, zVariant, decompositionDict,
                        componentDict):
                    yield {'ChineseCharacter': char, 'ZVariant': zVariant,
                        'Component': component,
                        'ComponentZVariant': componentZVariant}

    PROVIDES = 'ComponentLookup'
    DEPENDS = ['CharacterDecomposition']

    COLUMNS = ['ChineseCharacter', 'ZVariant', 'Component', 'ComponentZVariant']
    PRIMARY_KEYS = COLUMNS
    INDEX_KEYS = [['Component']]
    COLUMN_TYPES = {'ChineseCharacter': String(1), 'ZVariant': Integer(),
        'Component': String(1), 'ComponentZVariant': Integer()}

    def getGenerator(self):
        decompositionTable = self.db.tables['CharacterDecomposition']
        characterSet = set(self.db.selectRows(
            select([decompositionTable.c.ChineseCharacter,
                decompositionTable.c.ZVariant], distinct=True)))
        return CharacterComponentLookupBuilder.CharacterComponentGenerator(
            self.db, characterSet).generator()


class CharacterRadicalStrokeCountBuilder(EntryGeneratorBuilder):
    """
    Builds a mapping between characters and their radical with stroke count of
    residual components.

    This class can be extended by inheriting
    L{CharacterRadicalStrokeCountGenerator} and overwriting
    L{CharacterRadicalStrokeCountGenerator.getFormRadicalIndex()} to implement
    which forms should be regarded as radicals as well as
    L{CharacterRadicalStrokeCountGenerator.filterForms()} to filter entries
    before creation.
    """
    class CharacterRadicalStrokeCountGenerator:
        """Generates the character to radical/residual stroke count mapping."""

        def __init__(self, dbConnectInst, characterSet, quiet=False):
            """
            Initialises the CharacterRadicalStrokeCountGenerator.

            @type dbConnectInst: instance
            @param dbConnectInst: instance of a L{DatabaseConnector}
            @type characterSet: set
            @param characterSet: set of characters to generate the table for
            @type quiet: bool
            @param quiet: if true no status information will be printed to
                stderr
            """
            self.characterSet = characterSet
            self.quiet = quiet
            self.cjkDict = {}
            for loc in ['T', 'C', 'J', 'K', 'V']:
                self.cjkDict[loc] = characterlookup.CharacterLookup(loc,
                    dbConnectInst=dbConnectInst)
            self.radicalForms = None

        def getFormRadicalIndex(self, form):
            """
            Returns the Kangxi radical index for the given component.

            @type form: str
            @param form: component
            @rtype: int
            @return: radical index of the given radical form.
            """
            if self.radicalForms == None:
                self.radicalForms = {}
                for loc in ['T', 'C', 'J', 'K', 'V']:
                    for radicalIdx in range(1, 215):
                        for f in \
                            self.cjkDict[loc]\
                                .getKangxiRadicalRepresentativeCharacters(
                                    radicalIdx):
                            self.radicalForms[f] = radicalIdx

            if form not in self.radicalForms:
                return None
            return self.radicalForms[form]

        def filterForms(self, formSet):
            u"""
            Filters the set of given radical form entries to return only one
            single occurrence of a radical.

            @type formSet: set of dict
            @param formSet: radical/residual stroke count entries as generated
                by L{getEntries()}.
            @rtype: set of dict
            @return: subset of input
            @todo Lang: On multiple occurrences of same radical (may be in
                different forms): Which one to choose? Implement to turn down
                unwanted forms.
            """
            return formSet

        def getEntries(self, char, zVariant, strokeCountDict, decompositionDict,
            entriesDict):
            u"""
            Gets all radical/residual stroke count combinations from the given
            decomposition.

            @rtype: list
            @return: all radical/residual stroke count combinations for the
                character
            @raise ValueError: if IDS is malformed or ambiguous residual stroke
                count is calculated
            @todo Fix:  Remove validity check, only needed as long
                decomposition entries aren't checked against stroke order
                entries.
            """
            def getCharLayout(mainCharacterLayout, mainLayoutPosition,
                subCharLayout, subLayoutPosition):
                u"""
                Returns the character layout for the radical form within the
                component with layout subCharLayout itself belonging to a parent
                char with layout mainCharacterLayout.
                E.g. 鸺 can be decomposed into ⿰休鸟 and 休 can be furthermore
                decomposed into ⿰亻木. 亻 is found in a lower layer of
                decomposition, but as the structure of 休 and 鸺 are the same,
                and 亻 is on the left side of 休 which is on the left side of 鸺
                one can deduce 亻 as being on the utmost left side of 鸺. Thus
                (⿰, 0) would be returned.
                """
                specialReturn = {
                    (u'⿰', 0, u'⿰', 0): (u'⿰', 0),
                    (u'⿰', 1, u'⿰', 1): (u'⿰', 1),
                    (u'⿱', 0, u'⿱', 0): (u'⿱', 0),
                    (u'⿱', 1, u'⿱', 1): (u'⿱', 1),
                    (u'⿲', 0, u'⿲', 0): (u'⿰', 0),
                    (u'⿲', 2, u'⿲', 2): (u'⿰', 1),
                    (u'⿳', 0, u'⿳', 0): (u'⿱', 0),
                    (u'⿳', 2, u'⿳', 2): (u'⿱', 0),
                    (u'⿲', 0, u'⿰', 0): (u'⿰', 0),
                    (u'⿲', 2, u'⿰', 1): (u'⿰', 1),
                    (u'⿰', 0, u'⿲', 0): (u'⿰', 0),
                    (u'⿰', 1, u'⿲', 1): (u'⿰', 1),
                    (u'⿳', 0, u'⿱', 0): (u'⿱', 0),
                    (u'⿳', 2, u'⿱', 1): (u'⿱', 1),
                    (u'⿱', 0, u'⿳', 0): (u'⿱', 0),
                    (u'⿱', 1, u'⿳', 2): (u'⿱', 1),
                    }
                entry = (mainCharacterLayout, mainLayoutPosition, subCharLayout,
                    subLayoutPosition)
                if entry in specialReturn:
                    return specialReturn[entry]
                elif subCharLayout == u'⿻':
                    # default value for complex position
                    return (u'⿻', 0)
                elif mainCharacterLayout == None:
                    # main layout
                    return subCharLayout, subLayoutPosition
                else:
                    # radical component has complex position
                    return (u'⿻', 0)

            # if no decomposition available then there is nothing to do
            if (char, zVariant) not in decompositionDict:
                return []

            if (char, zVariant) not in entriesDict:
                entriesDict[(char, zVariant)] = set()

                for decomposition in decompositionDict[(char, zVariant)]:
                    componentRadicalForms = []
                    # if a radical is found in a subcharacter an entry is added
                    #   containing the radical form, its variant, the stroke
                    #   count of residual characters in this main character and
                    #   it's position in the main char (e.g. for 鸺 contains
                    #   Form 鸟, Z-variant 0, residual stroke count 6, main
                    #   layout ⿰ and position 1 (right side), as 亻 and 木
                    #   together form the residual components, and the
                    #   simplified structure of 鸺 applies to a left/right
                    #   model, with 鸟 being at the 2nd position.

                    # get all radical entries

                    # layout stack which holds the IDS operators and a position
                    #   in the IDS operator itself for each Chinese character
                    layoutStack = [(None, None)]

                    for entry in decomposition:
                        try:
                            layout, position = layoutStack.pop()
                        except IndexError:
                            raise ValueError(
                                "malformed IDS for character '%s'" % char)

                        if type(entry) != types.TupleType:
                            # ideographic description character found, derive
                            #   layout from IDS and parent character and store
                            #   in layout stack to be consumed by following
                            #   Chinese characters
                            if characterlookup.CharacterLookup\
                                .isTrinaryIDSOperator(entry):
                                posRange = [2, 1, 0]
                            else:
                                posRange = [1, 0]

                            for componentPos in posRange:
                                # append to stack one per following element,
                                #   adapt layout to parent one
                                layoutStack.append(getCharLayout(layout,
                                    position, entry, componentPos))
                        else:
                            # Chinese character found
                            componentChar, componentZVariant = entry

                            # create entries for this component
                            radicalIndex \
                                = self.getFormRadicalIndex(componentChar)
                            if radicalIndex != None:
                                # main component is radical, no residual stroke
                                #   count, save relative position in main
                                #   character
                                componentRadicalForms.append(
                                    {'Component': entry,
                                    'Form': componentChar,
                                    'Z-variant': componentZVariant,
                                    'ResidualStrokeCount': 0,
                                    'CharacterLayout': layout,
                                    'RadicalIndex': radicalIndex,
                                    'RadicalPosition': position})

                            # get all radical forms for this entry from
                            #   sub-components
                            for radicalEntry in self.getEntries(componentChar,
                                componentZVariant, strokeCountDict,
                                decompositionDict, entriesDict):

                                # get layout for this character wrt parent char
                                charLayout, charPosition = getCharLayout(layout,
                                    position, radicalEntry['CharacterLayout'],
                                    radicalEntry['RadicalPosition'])
                                componentEntry = radicalEntry.copy()
                                componentEntry['Component'] = entry
                                componentEntry['CharacterLayout'] = charLayout
                                componentEntry['RadicalPosition'] = charPosition
                                componentRadicalForms.append(componentEntry)

                    # for each character get the residual characters first
                    residualCharacters = {}
                    charactersSeen = []
                    for entry in decomposition:
                        # get Chinese characters
                        if type(entry) == types.TupleType:
                            # fill up already seen characters with next found
                            for seenEntry in residualCharacters:
                                residualCharacters[seenEntry].append(entry)

                            # set current character to already seen ones
                            residualCharacters[entry] = charactersSeen[:]

                            charactersSeen.append(entry)

                    # calculate residual stroke count and create entries
                    for componentEntry in componentRadicalForms:
                        # residual stroke count is the sum of the component's
                        #   residual stroke count (with out radical) and count
                        #   of the other components
                        for entry in \
                            residualCharacters[componentEntry['Component']]:

                            if entry not in strokeCountDict:
                                break

                            componentEntry['ResidualStrokeCount'] \
                                += strokeCountDict[entry]
                        else:
                            # all stroke counts available
                            del componentEntry['Component']
                            entriesDict[(char, zVariant)].add(
                                frozenset(componentEntry.items()))

                # validity check # TODO only needed as long decomposition and
                #   stroke order entries aren't checked for validity
                seenEntriesDict = {}
                for entry in [dict(d) for d in entriesDict[(char, zVariant)]]:
                    keyEntry = (entry['Form'], entry['Z-variant'],
                        entry['CharacterLayout'], entry['RadicalIndex'],
                        entry['RadicalPosition'])
                    if keyEntry in seenEntriesDict \
                        and seenEntriesDict[keyEntry] \
                            != entry['ResidualStrokeCount']:
                        raise ValueError(
                            "ambiguous residual stroke count for " \
                            + "character '%s' with entry '" % char \
                            + "', '".join(list([unicode(column) \
                                for column in keyEntry])) \
                            + "': '" + str(seenEntriesDict[keyEntry]) + "'/'" \
                            + str(entry['ResidualStrokeCount']) + "'")
                    seenEntriesDict[keyEntry] = entry['ResidualStrokeCount']

            # filter forms, i.e. for multiple radical occurrences prefer one
            return self.filterForms(
                [dict(d) for d in entriesDict[(char, zVariant)]])

        def generator(self):
            """Provides the radical/stroke count entries."""
            strokeCountDict = self.cjkDict['T'].getStrokeCountDict()
            decompositionDict = self.cjkDict['T'].getDecompositionEntriesDict()
            entryDict = {}

            for char, zVariant in self.characterSet:
                if self.cjkDict['T'].isRadicalChar(char):
                    # ignore Unicode radical forms
                    continue

                for entry in self.getEntries(char, zVariant, strokeCountDict,
                    decompositionDict, entryDict):

                    yield [char, zVariant, entry['RadicalIndex'], entry['Form'],
                        entry['Z-variant'], entry['CharacterLayout'],
                        entry['RadicalPosition'], entry['ResidualStrokeCount']]

    PROVIDES = 'CharacterRadicalResidualStrokeCount'
    DEPENDS = ['CharacterDecomposition', 'StrokeCount', 'KangxiRadical',
        'KangxiRadicalIsolatedCharacter', 'RadicalEquivalentCharacter',
        'CharacterKangxiRadical', 'Strokes']

    COLUMNS = ['ChineseCharacter', 'ZVariant', 'RadicalIndex', 'RadicalForm',
        'RadicalZVariant', 'MainCharacterLayout', 'RadicalRelativePosition',
        'ResidualStrokeCount']
    PRIMARY_KEYS = ['ChineseCharacter', 'ZVariant', 'RadicalForm',
        'RadicalZVariant', 'MainCharacterLayout', 'RadicalRelativePosition']
    COLUMN_TYPES = {'ChineseCharacter': String(1), 'RadicalIndex': Integer(),
        'RadicalForm': String(1), 'ZVariant': Integer(),
        'RadicalZVariant': Integer(), 'MainCharacterLayout': String(1),
        'RadicalRelativePosition': Integer(), 'ResidualStrokeCount': Integer()}

    def getGenerator(self):
        # get all characters we have component information for
        decompositionTable = self.db.tables['CharacterDecomposition']
        characterSet = set(self.db.selectRows(
            select([decompositionTable.c.ChineseCharacter,
                decompositionTable.c.ZVariant], distinct=True)))
        return CharacterRadicalStrokeCountBuilder\
            .CharacterRadicalStrokeCountGenerator(self.db, characterSet,
                self.quiet).generator()


class CharacterResidualStrokeCountBuilder(EntryGeneratorBuilder):
    """
    Builds a mapping between characters and their residual stroke count when
    splitting of the radical form. This is stripped off information gathered
    from table C{CharacterRadicalStrokeCount}.
    """
    class ResidualStrokeCountExtractor:
        """
        Generates the character to residual stroke count mapping from the
        C{CharacterRadicalResidualStrokeCount} table.
        """
        def __init__(self, dbConnectInst, characterSet):
            """
            Initialises the ResidualStrokeCountExtractor.

            @type dbConnectInst: instance
            @param dbConnectInst: instance of a L{DatabaseConnector}
            @type characterSet: set
            @param characterSet: set of characters to generate the table for
            """
            self.characterSet = characterSet
            # create instance, locale is not important, we supply own zVariant
            self.cjk = characterlookup.CharacterLookup('T',
                dbConnectInst=dbConnectInst)

        def getEntries(self, char, zVariant, radicalDict):
            u"""
            Gets a list of radical residual entries. For multiple radical
            occurrences (e.g. 伦) only returns the residual stroke count for the
            "main" radical form.

            @type char: str
            @param char: Chinese character
            @type zVariant: int
            @param zVariant: I{Z-variant} of given character
            @rtype: list of tuple
            @return: list of residual stroke count entries
            @todo Lang: Implement, find a good algorithm to turn down unwanted
                forms, don't just choose random one. See the following list::

                >>> from cjklib import characterlookup
                >>> cjk = characterlookup.CharacterLookup('T')
                >>> for char in cjk.db.selectSoleValue('CharacterRadicalResidualStrokeCount',
                ...     'ChineseCharacter', distinctValues=True):
                ...     try:
                ...         entries = cjk.getCharacterKangxiRadicalResidualStrokeCount(char, 'C')
                ...         lastEntry = entries[0]
                ...         for entry in entries[1:]:
                ...             # print if diff. radical forms and diff. residual stroke count
                ...             if lastEntry[0] != entry[0] and lastEntry[2] != entry[2]:
                ...                 print char
                ...                 break
                ...             lastEntry = entry
                ...     except:
                ...         pass
                ...
                渌
                犾
                玺
                珏
                缧
                >>> cjk.getCharacterKangxiRadicalResidualStrokeCount(u'缧')
                [(u'\u7cf8', 0, u'\u2ffb', 0, 8), (u'\u7e9f', 0, u'\u2ff0', 0, 11)]
            """
            # filter entries to return only the main radical form
            # TODO provisional solution, take first entry per radical index
            filteredEntries = []
            for radicalIdx in radicalDict[(char, zVariant)]:
                _, _, _, _, residualStrokeCount \
                    = radicalDict[(char, zVariant)][radicalIdx][0]
                filteredEntries.append((radicalIdx, residualStrokeCount))

            return filteredEntries

        def generator(self):
            """Provides one entry per character, z-Variant and locale subset."""
            radicalDict = self.cjk.getCharacterRadicalResidualStrokeCountDict()
            for char, zVariant in self.characterSet:
                for radicalIndex, residualStrokeCount in self.getEntries(char,
                    zVariant, radicalDict):
                    yield [char, zVariant, radicalIndex, residualStrokeCount]

    PROVIDES = 'CharacterResidualStrokeCount'
    DEPENDS = ['CharacterRadicalResidualStrokeCount']

    COLUMNS = ['ChineseCharacter', 'ZVariant', 'RadicalIndex',
        'ResidualStrokeCount']
    PRIMARY_KEYS = ['ChineseCharacter', 'ZVariant', 'RadicalIndex']
    INDEX_KEYS = [['RadicalIndex']]
    COLUMN_TYPES = {'ChineseCharacter': String(1), 'RadicalIndex': Integer(),
        'ZVariant': Integer(), 'ResidualStrokeCount': Integer()}

    def getGenerator(self):
        residualSCTable = self.db.tables['CharacterRadicalResidualStrokeCount']
        characterSet = set(self.db.selectRows(
            select([residualSCTable.c.ChineseCharacter,
                residualSCTable.c.ZVariant], distinct=True)))
        return CharacterResidualStrokeCountBuilder.ResidualStrokeCountExtractor(
            self.db, characterSet).generator()


class CombinedCharacterResidualStrokeCountBuilder(
    CharacterResidualStrokeCountBuilder):
    """
    Builds a mapping between characters and their residual stroke count when
    splitting of the radical form. Includes stroke count data from the Unihan
    database to make up for missing data in own data files.
    """
    class CombinedResidualStrokeCountExtractor:
        """
        Generates the character to residual stroke count mapping.
        """
        RADICAL_REGEX = re.compile(ur"(\d+)\.(\d+)")

        def __init__(self, tableEntries, preferredBuilder, quiet=False):
            """
            Initialises the CombinedResidualStrokeCountExtractor.

            @type tableEntries: list of list
            @param tableEntries: list of characters with Z-variant
            @type preferredBuilder: instance
            @param preferredBuilder: TableBuilder which forms are preferred over
                entries from the Unihan table
            @type quiet: bool
            @param quiet: if true no status information will be printed
            """
            self.tableEntries = tableEntries
            self.preferredBuilder = preferredBuilder
            self.quiet = quiet

        def generator(self):
            """Provides one entry per character and z-Variant."""
            # handle chars from own data first
            seenCharactersSet = set()
            for entry in self.preferredBuilder:
                yield entry
                char = entry[0]
                radicalIdx = entry[2]
                seenCharactersSet.add((char, radicalIdx))

            # now fill up with characters from Unihan, Z-variant missing though
            for char, radicalStroke in self.tableEntries:
                matchObj = self.RADICAL_REGEX.match(radicalStroke)
                if matchObj:
                    try:
                        radicalIndex = int(matchObj.group(1))
                        residualStrokeCount = int(matchObj.group(2))
                        if (char, radicalIndex) not in seenCharactersSet:
                            yield [char, 0, radicalIndex, residualStrokeCount]
                        continue
                    except ValueError:
                        pass

                if not self.quiet:
                    warn("unable to read radical information of " \
                        + "character '%s': '%s'" % (char, radicalStroke))

    DEPENDS = ['CharacterRadicalResidualStrokeCount', 'Unihan']
    COLUMN_SOURCE = 'kRSKangXi'

    def getGenerator(self):
        residualSCTable = self.db.tables['CharacterRadicalResidualStrokeCount']
        characterSet = set(self.db.selectRows(
            select([residualSCTable.c.ChineseCharacter,
                residualSCTable.c.ZVariant], distinct=True)))
        preferredBuilder = CombinedCharacterResidualStrokeCountBuilder\
            .ResidualStrokeCountExtractor(self.db, characterSet).generator()

        # get main builder
        unihanTable = self.db.tables['Unihan']
        tableEntries = set(self.db.selectRows(
            select([unihanTable.c.ChineseCharacter,
                unihanTable.c[self.COLUMN_SOURCE]],
                unihanTable.c[self.COLUMN_SOURCE] != None)))
        return CombinedCharacterResidualStrokeCountBuilder\
            .CombinedResidualStrokeCountExtractor(tableEntries,
                preferredBuilder, self.quiet).generator()

#}
#{ Dictionary builder

class EDICTFormatBuilder(EntryGeneratorBuilder):
    """
    Provides an abstract class for loading EDICT formatted dictionaries.

    One column will be provided for the headword, one for the reading (in EDICT
    that is the Kana) and one for the translation.
    @todo Fix: Optimize insert, use transaction which disables autocommit and
        cosider passing data all at once, requiring proper handling of row
        indices.
    """
    class TableGenerator:
        """Generates the dictionary entries."""

        def __init__(self, fileHandle, quiet=False, entryRegex=None,
            columns=None, filterFunc=None):
            """
            Initialises the TableGenerator.

            @type fileHandle: file
            @param fileHandle: handle of file to read from
            @type quiet: bool
            @param quiet: if true no status information will be printed
            @type entryRegex: instance
            @param entryRegex: regular expression object for entry pattern
            @type columns: list of str
            @param columns: column names of generated data
            @type filterFunc: function
            @param filterFunc: function used to filter entry content
            """
            self.fileHandle = fileHandle
            self.quiet = quiet
            self.columns = columns
            self.filterFunc = filterFunc
            if entryRegex:
                self.entryRegex = entryRegex
            else:
                # the EDICT dictionary itself omits the KANA in brackets if
                # the headword is already a KANA word
                # KANJI [KANA] /english_1/english_2/.../
                # KANA /english_1/.../
                self.entryRegex = \
                    re.compile(r'\s*(\S+)\s*(?:\[([^\]]*)\]\s*)?(/.*/)\s*$')

        def generator(self):
            """Provides the dictionary entries."""
            for line in self.fileHandle:
                # ignore comments
                if line.lstrip().startswith('#'):
                    continue
                # parse line
                matchObj = self.entryRegex.match(line)
                if not matchObj:
                    if not self.quiet and line.strip() != '':
                        warn("error reading line '" + line + "'")
                    continue
                # get entries
                entry = matchObj.groups()
                if self.columns:
                    entry = dict([(self.columns[idx], cell) for idx, cell \
                        in enumerate(entry)])
                if self.filterFunc:
                    entry = self.filterFunc(entry)
                yield entry

    COLUMNS = ['Headword', 'Reading', 'Translation']
    PRIMARY_KEYS = []
    INDEX_KEYS = [['Headword'], ['Reading']]
    COLUMN_TYPES = {'Headword': String(255), 'Reading': String(255),
        'Translation': Text()}

    FULLTEXT_COLUMNS = ['Translation']
    """Column names which shall be fulltext searchable."""
    FILE_NAMES = None
    """Names of file containing the edict formated dictionary."""
    ENCODING = 'utf-8'
    """Encoding of the dictionary file."""
    ENTRY_REGEX = None
    """
    Regular Expression matching a dictionary entry. Needs to be overwritten if
    not strictly follows the EDICT format.
    """
    IGNORE_LINES = 0
    """Number of starting lines to ignore."""
    FILTER = None
    """Filter to apply to the read entry before writing to table."""

    def __init__(self, **options):
        """
        Constructs the EDICTFormatBuilder.

        @param options: extra options
        @keyword dbConnectInst: instance of a L{DatabaseConnector}
        @keyword dataPath: optional list of paths to the data file(s)
        @keyword quiet: if C{True} no status information will be printed to
            stderr
        @keyword enableFTS3: if C{True} SQLite full text search (FTS3) will be
            supported, if the extension exists.
        @keyword filePath: file path including file name, overrides dataPath
        @keyword fileType: type of file (.zip, .tar, .tar.bz2, .tar.gz, .gz,
            .txt),
            overrides file type guessing
        """
        super(EDICTFormatBuilder, self).__init__(**options)

        if self.fileType and self.fileType not in ('.zip', '.tar', '.tar.bz2',
            '.tar.gz', '.gz', '.txt'):
            raise ValueError('Unknown file type "%s"' % self.fileType)

    @classmethod
    def getDefaultOptions(cls):
        options = super(EDICTFormatBuilder, cls).getDefaultOptions()
        options.update({'enableFTS3': True, 'filePath': None,
            'fileType': None})

        return options

    @classmethod
    def getOptionMetaData(cls, option):
        optionsMetaData = {'enableFTS3': {'type': 'bool',
                'description': "enable SQLite full text search (FTS3)"},
            'filePath': {'type': 'string', 'description': \
                "file path including file name, overrides searching"},
            'fileType': {'type': 'choice',
                'choices': ('.zip', '.tar', '.tar.bz2', '.tar.gz', '.gz',
                    '.txt'),
                'description': "file extension, overrides file type guessing"}}

        if option in optionsMetaData:
            return optionsMetaData[option]
        else:
            return super(EDICTFormatBuilder, cls).getOptionMetaData(option)

    def getGenerator(self):
        # get file handle
        if  self.filePath:
            filePath =  self.filePath
        else:
            filePath = self.findFile(self.FILE_NAMES)

        handle = self.getFileHandle(filePath)
        if not self.quiet:
            warn("Reading table from file '" + filePath + "'")

        # ignore starting lines
        for _ in range(0, self.IGNORE_LINES):
            handle.readline()
        # create generator
        return EDICTFormatBuilder.TableGenerator(handle, self.quiet,
            self.ENTRY_REGEX, self.COLUMNS, self.FILTER).generator()

    def getArchiveContentName(self, nameList, filePath):
        """
        Function extracting the name of contained file from the zipped/tared
        archive using the file name.
        Reimplement and adapt to own needs.

        @type nameList: list of str
        @param nameList: list of archive contents
        @type filePath: str
        @param filePath: path of file
        @rtype: str
        @return: name of file in archive
        """
        fileName = os.path.basename(filePath)
        fileRoot, _ = os.path.splitext(fileName)
        return fileRoot

    def getFileHandle(self, filePath):
        """
        Returns a handle to the give file.

        The file can be either normal content, zip, tar, .tar.gz, tar.bz2

        @type filePath: str
        @param filePath: path of file
        @rtype: file
        @return: handle to file's content
        """
        import zipfile
        import tarfile

        if self.fileType == '.zip' \
            or not self.fileType and zipfile.is_zipfile(filePath):
            import StringIO
            z = zipfile.ZipFile(filePath, 'r')
            archiveContent = self.getArchiveContentName(z.namelist(), filePath)
            return StringIO.StringIO(z.read(archiveContent)\
                .decode(self.ENCODING))
        elif self.fileType in ('.tar', '.tar.bz2', '.tar.gz') \
            or not self.fileType and tarfile.is_tarfile(filePath):
            import StringIO
            mode = ''
            ending = self.fileType or filePath
            if ending.endswith('bz2'):
                mode = ':bz2'
            elif ending.endswith('gz'):
                mode = ':gz'
            z = tarfile.open(filePath, 'r' + mode)
            archiveContent = self.getArchiveContentName(z.getnames(), filePath)
            fileObj = z.extractfile(archiveContent)
            return StringIO.StringIO(fileObj.read().decode(self.ENCODING))
        elif self.fileType == '.gz' \
            or not self.fileType and filePath.endswith('.gz'):
            import gzip
            import StringIO
            z = gzip.GzipFile(filePath, 'r')
            return StringIO.StringIO(z.read().decode(self.ENCODING))
        else:
            import codecs
            return codecs.open(filePath, 'r', self.ENCODING)

    def buildFTS3CreateTableStatement(self, table):
        """
        Returns a SQL statement for creating a virtual table using FTS3 for
        SQLite.

        @type table: object
        @param table: SQLAlchemy table object representing the FTS3 table
        @rtype: str
        @return: Create table statement
        """
        preparer = self.db.engine.dialect.identifier_preparer

        preparedColumns = []
        for column in table.columns:
            preparedColumns.append(preparer.format_column(column))
        preparedTableName = preparer.format_table(table)
        return text("CREATE VIRTUAL TABLE %s USING FTS3(%s);" \
            % (preparedTableName, ', '.join(preparedColumns)))

    def buildFTS3Tables(self, tableName, columns, columnTypeMap=None,
        primaryKeys=None, fullTextColumns=None):
        """
        Builds a FTS3 table construct for supporting full text search under
        SQLite.

        @type tableName: str
        @param tableName: name of table
        @type columns: list of str
        @param columns: column names
        @type columnTypeMap: dict of str and object
        @param columnTypeMap: mapping of column name to SQLAlchemy Column
        @type primaryKeys: list of str
        @param primaryKeys: list of primary key columns
        @type fullTextColumns: list of str
        @param fullTextColumns: list of fulltext columns
        """
        columnTypeMap = columnTypeMap or {}
        primaryKeys = primaryKeys or []
        fullTextColumns = fullTextColumns or []

        # table with non-FTS3 data
        simpleColumns = [column for column in columns \
            if column not in fullTextColumns]
        simpleTable = self.buildTableObject(tableName + '_Normal',
            simpleColumns, columnTypeMap, primaryKeys)
        simpleTable.create()

        # FTS3 table
        fts3Table = self.buildTableObject(tableName + '_Text', fullTextColumns,
            columnTypeMap)
        createFTS3Statement = self.buildFTS3CreateTableStatement(fts3Table)
        self.db.execute(createFTS3Statement)

        # view to mask FTS3 table construct as simple table
        view = Table(tableName, self.db.metadata)
        preparer = self.db.engine.dialect.identifier_preparer
        simpleTableName = preparer.format_table(simpleTable)
        fts3TableName = preparer.format_table(fts3Table)

        createViewStatement = text("""CREATE VIEW %s AS SELECT * FROM %s JOIN %s
            ON %s.rowid = %s.rowid;""" \
                % (preparer.format_table(view), simpleTableName, fts3TableName,
                    simpleTableName, fts3TableName))
        self.db.execute(createViewStatement)
        # register view so processes depending on this succeed, see special
        #   view handling in DatabaseBuilder.__init__, workaround for SQLalchemy
        # TODO Bug in SQLalchemy that doesn't reflect table on reload?
        #   http://www.sqlalchemy.org/trac/ticket/1410
        #t = Table(tableName, self.db.metadata, autoload=True, useexisting=True)
        self.db.engine.reflecttable(view)

    def insertFTS3Tables(self, tableName, generator, columns=None,
        fullTextColumns=None):

        columns = columns or []
        fullTextColumns = fullTextColumns or []

        simpleColumns = [column for column in columns \
            if column not in fullTextColumns]
        simpleTable = Table(tableName + '_Normal', self.db.metadata,
            autoload=True)
        fts3Table = Table(tableName + '_Text', self.db.metadata,
            autoload=True)
        fts3FullRows = ['rowid']
        fts3FullRows.extend(fullTextColumns)

        for newEntry in generator:
            try:
                if type(newEntry) == type([]):
                    simpleData = [newEntry[i] \
                        for i, column in enumerate(columns) \
                            if column not in fullTextColumns]
                    fts3Data = [newEntry[i] \
                        for i, column in enumerate(columns) \
                            if column in fullTextColumns]
                    fts3Data.insert('rowid', 0)
                else:
                    simpleData = dict([(key, value) \
                        for key, value in newEntry.items() \
                        if key in simpleColumns])
                    fts3Data = dict([(key, value) \
                        for key, value in newEntry.items() \
                        if key in fullTextColumns])
                    fts3Data['rowid'] = func.last_insert_rowid()

                # table with non-FTS3 data
                simpleTable.insert(simpleData).execute()
                fts3Table.insert(fts3Data).execute()
            except IntegrityError, e:
                if not self.quiet:
                    warn(unicode(e))
                    #warn(unicode(insertStatement))
                raise

    def testFTS3(self):
        """
        Tests if the SQLite FTS3 extension is supported on the build system.

        @rtype: bool
        @return: C{True} if the FTS3 extension exists, C{False} otherwise.
        """
        # Until #3436 is fixed (http://www.sqlite.org/cvstrac/tktview?tn=3436,5)
        #   do it the bad way
        try:
            dummyTable = Table('cjklib_test_fts3_presence', self.db.metadata,
                Column('dummy'), useexisting=True)
            createStatement = self.buildFTS3CreateTableStatement(dummyTable)
            self.db.execute(createStatement)
            try:
                dummyTable.drop()
            except OperationalError:
                pass
            return True
        except OperationalError:
            return False

    def build(self):
        """
        Build the table provided by the TableBuilder.

        A search index is created to allow for fulltext searching.
        """
        # get generator, might raise an Exception if source not found
        generator = self.getGenerator()

        hasFTS3 = self.enableFTS3 and self.db.engine.name == 'sqlite' \
            and self.testFTS3()
        if not hasFTS3:
            if not self.quiet:
                if not self.enableFTS3:
                    reason = 'deactivated by user.'
                elif self.db.engine.name != 'sqlite':
                    reason = 'not supported by database engine.'
                else:
                    reason = 'extension not found.'
                warn("SQLite FTS3 fulltext search disabled: %s" % reason)
            # get create statement
            table = self.buildTableObject(self.PROVIDES, self.COLUMNS,
                self.COLUMN_TYPES, self.PRIMARY_KEYS)
            table.create()
        else:
            # get create statement
            self.buildFTS3Tables(self.PROVIDES, self.COLUMNS, self.COLUMN_TYPES,
                self.PRIMARY_KEYS, self.FULLTEXT_COLUMNS)

        if not hasFTS3:
            # write table content
            #try:
                #entries = self.getEntryDict(generator)
                #self.db.execute(table.insert(), entries)
            #except IntegrityError, e:
                #warn(unicode(e))
                ##warn(unicode(insertStatement))
                #raise
            for newEntry in generator:
                try:
                    table.insert(newEntry).execute()
                except IntegrityError, e:
                    if not self.quiet:
                        warn(unicode(e))
                        #warn(unicode(insertStatement))
                    raise
        else:
            # write table content
            self.insertFTS3Tables(self.PROVIDES, generator, self.COLUMNS,
                self.FULLTEXT_COLUMNS)

        # get create index statement
        if not hasFTS3:
            for index in self.buildIndexObjects(self.PROVIDES, self.INDEX_KEYS):
                index.create()
        else:
            for index in self.buildIndexObjects(self.PROVIDES + '_Normal',
                self.INDEX_KEYS):
                index.create()

    def remove(self):
        # get drop table statement

        hasFTS3 = self.db.engine.has_table(self.PROVIDES + '_Text')
        if not hasFTS3:
            table = Table(self.PROVIDES, self.db.metadata)
            table.drop()
            self.db.metadata.remove(table)
        else:
            preparer = self.db.engine.dialect.identifier_preparer
            view = Table(self.PROVIDES, self.db.metadata)
            dropViewStatement = text("DROP VIEW %s" \
                % preparer.format_table(view))
            self.db.execute(dropViewStatement)
            self.db.metadata.remove(view)
            table = Table(self.PROVIDES + '_Normal', self.db.metadata)
            table.drop()
            self.db.metadata.remove(table)
            table = Table(self.PROVIDES + '_Text', self.db.metadata)
            table.drop()
            self.db.metadata.remove(table)


class WordIndexBuilder(EntryGeneratorBuilder):
    """
    Builds a translation word index for a given dictionary.

    Searching for a word will return a headword and reading. This allows to find
    several dictionary entries with same headword and reading, with only one
    including the translation word.

    @todo Fix:  Word regex is specialised for HanDeDict.
    @todo Fix:  Using a row_id for joining instead of Headword(Traditional) and
        Reading would maybe speed up table joins. Needs a workaround to include
        multiple rows for one actual headword entry though.
    """
    class WordEntryGenerator:
        """Generates words for a list of dictionary entries."""

        def __init__(self, entries):
            """
            Initialises the WordEntryGenerator.

            @type entries: list of tuple
            @param entries: a list of headword and its translation
            """
            self.entries = entries
            # TODO this regex is adapted to HanDeDict, might be not general
            #   enough
            self.wordRegex = re.compile(r'\([^\)]+\)|' \
                + r'(?:; Bsp.: [^/]+?--[^/]+)|([^/,\(\)\[\]\!\?]+)')

        def generator(self):
            """Provides all data of one word per entry."""
            # remember seen entries to prevent double entries
            seenWordEntries = set()
            newEntryDict = {}

            for headword, reading, translation in self.entries:
                newEntryDict['Headword'] = headword
                newEntryDict['Reading'] = reading
                for word in self.wordRegex.findall(translation):
                    word = word.strip().lower()
                    if not word:
                        continue
                    if word \
                        and (headword, reading, word) not in seenWordEntries:
                        seenWordEntries.add((headword, reading, word))
                        newEntryDict['Word'] = word
                        yield newEntryDict

    COLUMNS = ['Headword', 'Reading', 'Word']
    COLUMN_TYPES = {'Headword': String(255), 'Reading': String(255),
        'Word': String(255)}
    INDEX_KEYS = [['Word']]

    TABLE_SOURCE = None
    """Dictionary source"""
    HEADWORD_SOURCE = 'Headword'
    """Source of headword"""

    def getGenerator(self):
        table = self.db.tables[self.TABLE_SOURCE]
        entries = self.db.selectRows(
            select([table.c[self.HEADWORD_SOURCE], table.c.Reading,
                table.c.Translation]))
        return WordIndexBuilder.WordEntryGenerator(entries).generator()


class EDICTBuilder(EDICTFormatBuilder):
    """
    Builds the EDICT dictionary.
    """
    PROVIDES = 'EDICT'
    FILE_NAMES = ['edict.gz', 'edict.zip', 'edict']
    ENCODING = 'euc-jp'
    IGNORE_LINES = 1


class EDICTWordIndexBuilder(WordIndexBuilder):
    """
    Builds the word index of the EDICT dictionary.
    """
    PROVIDES = 'EDICT_Words'
    DEPENDS = ['EDICT']
    TABLE_SOURCE = 'EDICT'


class CEDICTFormatBuilder(EDICTFormatBuilder):
    """
    Provides an abstract class for loading CEDICT formatted dictionaries.

    Two column will be provided for the headword (one for traditional and
    simplified writings each), one for the reading (e.g. in CEDICT Pinyin) and
    one for the translation.
    @todo Impl: Proper collation for Translation and Reading columns.
    """
    COLUMNS = ['HeadwordTraditional', 'HeadwordSimplified', 'Reading',
        'Translation']
    INDEX_KEYS = [['HeadwordTraditional'], ['HeadwordSimplified'], ['Reading']]
    COLUMN_TYPES = {'HeadwordTraditional': String(255),
        'HeadwordSimplified': String(255), 'Reading': String(255),
        'Translation': Text()}

    ENTRY_REGEX = re.compile(
        r'\s*(\S+)(?:\s+(\S+))?\s*\[([^\]]*)\]\s*(/.*/)\s*$')


class CEDICTBuilder(CEDICTFormatBuilder):
    """
    Builds the CEDICT dictionary.
    """
    def filterUmlaut(self, entry):
        """
        Converts the C{'u:'} to C{'ü'}.

        @type entry: tuple
        @param entry: a dictionary entry
        @rtype: tuple
        @return: the given entry with corrected ü-voul
        """
        if type(entry) == type({}):
            entry['Reading'] = entry['Reading'].replace('u:', u'ü')
            return entry
        else:
            trad, simp, reading, translation = entry
            reading = reading.replace('u:', u'ü')
            return [trad, simp, reading, translation]

    PROVIDES = 'CEDICT'
    FILE_NAMES = ['cedict_1_0_ts_utf-8_mdbg.zip',
        'cedict_1_0_ts_utf-8_mdbg.txt.gz', 'cedictu8.zip', 'cedict_ts.u8',
        'cedict_1_0_ts_utf-8_mdbg.txt']
    ENCODING = 'utf-8'
    FILTER = filterUmlaut

    def getArchiveContentName(self, nameList, filePath):
        return 'cedict_ts.u8'


class CEDICTWordIndexBuilder(WordIndexBuilder):
    """
    Builds the word index of the CEDICT dictionary.
    """
    PROVIDES = 'CEDICT_Words'
    DEPENDS = ['CEDICT']
    TABLE_SOURCE = 'CEDICT'
    HEADWORD_SOURCE = 'HeadwordTraditional'


class CEDICTGRBuilder(EDICTFormatBuilder):
    """
    Builds the CEDICT-GR dictionary.
    """
    PROVIDES = 'CEDICTGR'
    FILE_NAMES = ['cedictgr.zip', 'cedictgr.b5']
    ENCODING = 'big5hkscs'

    def getArchiveContentName(self, nameList, filePath):
        return 'cedictgr.b5'


class CEDICTGRWordIndexBuilder(WordIndexBuilder):
    """
    Builds the word index of the CEDICT-GR dictionary.
    """
    PROVIDES = 'CEDICTGR_Words'
    DEPENDS = ['CEDICTGR']
    TABLE_SOURCE = 'CEDICTGR'
    HEADWORD_SOURCE = 'Headword'


class TimestampedCEDICTFormatBuilder(CEDICTFormatBuilder):
    """
    Shared functionality for dictionaries whose file names include a timestamp.
    """
    EXTRACT_TIMESTAMP = None
    """Regular expression to extract the timestamp from the file name."""

    ARCHIVE_CONTENT_PATTERN = None
    """Regular expression specifying file in archive."""

    def extractTimeStamp(self, filePath):
        fileName = os.path.basename(filePath)
        matchObj = re.match(self.EXTRACT_TIMESTAMP, fileName)
        if matchObj:
            return matchObj.group(1)

    def getPreferredFile(self, filePaths):
        timeStamps = []
        for filePath in filePaths:
            ts = self.extractTimeStamp(filePath)
            if ts:
                timeStamps.append((ts, filePath))
        if timeStamps:
            _, filePath = max(timeStamps)
            return filePath
        else:
            return filePaths[0]

    def getArchiveContentName(self, nameList, filePath):
        for name in nameList:
            if re.match(self.ARCHIVE_CONTENT_PATTERN, name):
                return name

    def findFile(self, fileGlobs, fileType=None):
        """
        Tries to locate a file with a given list of possible file names under
        the classes default data paths.

        Uses the newest version of all files found.

        @type fileGlobs: str/list of str
        @param fileGlobs: possible file names
        @type fileType: str
        @param fileType: textual type of file used in error msg
        @rtype: str
        @return: path to file of first match in search for existing file
        @raise IOError: if no file found
        """
        import glob

        if type(fileGlobs) != type([]):
            fileGlobs = [fileGlobs]
        foundFiles = []
        for fileGlob in fileGlobs:
            for path in self.dataPath:
                globPath = os.path.join(os.path.expanduser(path), fileGlob)
                for filePath in glob.glob(globPath):
                    if os.path.exists(filePath):
                        fileName = os.path.basename(filePath)
                        foundFiles.append((fileName, filePath))

        if foundFiles:
            if hasattr(self, 'getPreferredFile'):
                return self.getPreferredFile([path for _, path in foundFiles])
            else:
                _, newestPath = max(foundFiles)
                return newestPath
        else:
            if fileType == None:
                fileType = "file"
            raise IOError("No " + fileType + " found for '" + self.PROVIDES \
                + "' under path(s)'" + "', '".join(self.dataPath) \
                + "' for file names '" + "', '".join(fileGlobs) + "'")


class HanDeDictBuilder(TimestampedCEDICTFormatBuilder):
    """
    Builds the HanDeDict dictionary.
    """
    def filterSpacing(self, entry):
        """
        Converts wrong spacing in readings of entries in HanDeDict.

        @type entry: tuple
        @param entry: a dictionary entry
        @rtype: tuple
        @return: the given entry with corrected spacing
        """
        if type(entry) == type({}):
            headword = entry['HeadwordTraditional']
            reading = entry['Reading']
        else:
            headword, headwordSimplified, reading, translation = entry

        readingEntities = []
        precedingIsNonReading = False
        for idx, entity in enumerate(reading.split(' ')):
            if idx < len(headword) and entity == headword[idx]:
                # for entities showing up in both strings, omit spaces
                #   (e.g. "IC卡", "I C kǎ")
                if not precedingIsNonReading:
                    readingEntities.append(' ')

                precedingIsNonReading = True
            elif idx != 0:
                readingEntities.append(' ')
                precedingIsNonReading = False

            readingEntities.append(entity)

        reading = ''.join(readingEntities)

        if type(entry) == type({}):
            entry['Reading'] = reading
            return entry
        else:
            return [headword, headwordSimplified, reading, translation]

    PROVIDES = 'HanDeDict'
    FILE_NAMES = ['handedict-*.zip', 'handedict-*.tar.bz2', 'handedict.u8']
    ENCODING = 'utf-8'
    FILTER = filterSpacing

    EXTRACT_TIMESTAMP = r'handedict-(\d{8})\.'
    ARCHIVE_CONTENT_PATTERN = r'handedict-(\d{8})/handedict.u8'


class HanDeDictWordIndexBuilder(WordIndexBuilder):
    """
    Builds the word index of the HanDeDict dictionary.
    """
    PROVIDES = 'HanDeDict_Words'
    DEPENDS = ['HanDeDict']
    TABLE_SOURCE = 'HanDeDict'
    HEADWORD_SOURCE = 'HeadwordTraditional'


class CFDICTBuilder(TimestampedCEDICTFormatBuilder):
    """
    Builds the CFDICT dictionary.
    """
    PROVIDES = 'CFDICT'
    FILE_NAMES = ['cfdict-*.zip', 'cfdict-*.tar.bz2', 'cfdict.u8']
    ENCODING = 'utf-8'

    EXTRACT_TIMESTAMP = r'cfdict-(\d{8})\.'
    ARCHIVE_CONTENT_PATTERN = r'cfdict-(\d{8})/cfdict.u8'


class CFDICTWordIndexBuilder(WordIndexBuilder):
    """
    Builds the word index of the CFDICT dictionary.
    """
    PROVIDES = 'CFDICT_Words'
    DEPENDS = ['CFDICT']
    TABLE_SOURCE = 'CFDICT'
    HEADWORD_SOURCE = 'HeadwordTraditional'
