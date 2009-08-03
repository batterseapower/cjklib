#!/usr/bin/python
# -*- coding: utf-8 -*-
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
Provides the central Chinese character based functions.
@todo Fix:  Move examples and scripts to use new layout of CharacterLookup.
    Don't mention a ValueError any more, as locale is specified at instantiation
    time.
"""

# import math
from sqlalchemy import select, union
from sqlalchemy.sql import and_, or_, not_

from cjklib import reading
from cjklib import exception
from cjklib import dbconnector

class CharacterLookup:
    u"""
    CharacterLookup provides access to lookup methods related to Han characters.

    The real system of CharacterLookup lies in the database beneath where all
    relevant data is stored. So for nearly all methods this class needs access
    to a database. Thus on initialisation of the object a connection to a
    database is established, the logic for this provided by the
    L{DatabaseConnector}.

    See the L{DatabaseConnector} for supported database systems.

    CharacterLookup will try to read the config file from either /etc or the
    users home folder. If none is present it will try to open a SQLite database
    stored as C{db} in the same folder by default. You can override this
    behaviour by specifying additional parameters on creation of the object.

    Examples
    ========
    The following examples should give a quick view into how to use this
    package.
        - Create the CharacterLookup object with default settings (read from
            cjklib.conf or 'cjklib.db' in same directory as default) and set
            the character locale to traditional:

            >>> from cjklib import characterlookup
            >>> cjk = characterlookup.CharacterLookup('T')

        - Get a list of characters, that are pronounced "국" in Korean:

            >>> cjk.getCharactersForReading(u'국', 'Hangul')
            [u'匊', u'國', u'局', u'掬', u'菊', u'跼', u'鞠', u'鞫', u'麯', u'麴']

        - Check if a character is included in another character as a component:

            >>> cjk.isComponentInCharacter(u'玉', u'宝')
            True

        - Get all Kangxi radical variants for Radical 184 (⾷) (under the
            traditional locale):

            >>> cjk.getKangxiRadicalVariantForms(184)
            [u'\u2ede', u'\u2edf']

    X{Character locale}
    ===================
    During the development of characters in the different cultures character
    appearances changed over time to that extent, that the handling of radicals,
    character components and strokes needs to be distinguished, depending on the
    locale.

    To deal with this circumstance I{CharacterLookup} works with a character
    locale. Most of the methods of this class need a locale context. In these
    cases the output of the method depends on the specified locale.

    For example in the traditional locale 这 has 8 strokes, but in
    simplified Chinese it has only 7, as the radical ⻌ has different stroke
    counts, depending on the locale.

    X{Z-variant}s
    =============
    One feature of Chinese characters is the glyph form describing the visual
    representation. This feature doesn't need to be unique and so many
    characters can be found in different writing variants e.g. character 福
    (English: luck) which has numerous forms.

    The Unicode Consortium does not include same characters of different
    actual shape in the Unicode standard (called I{Z-variant}s), except a few
    "double" entries which are included as to maintain backward compatibility.
    In fact a code point represents an abstract character not defining any
    visual representation. Thus a distinct appearance description including
    strokes and stroke order cannot be simply assigned to a code point but one
    needs to deal with the notion of I{Z-variants} representing distinct glyphs
    to which a visual description can be applied.

    The name Z-variant is derived from the three-dimensional model representing
    the space of characters relative to three axis, being the X axis
    representing the semantic space, the Y axis representing the abstract shape
    space and finally the Z axis for typeface differences (see "Principles of
    Han Unification" in: The Unicode Standard 5.0, chapter 12). Character
    presentations only differing in the Z dimension are generally unified.

    cjklib tries to offer a simple approach to handle different Z-variants. As
    character components, strokes and the stroke order depend on this variant,
    methods dealing with this kind will ask for a I{Z-variant} value to be
    specified. In these cases the output of the method depends on the specified
    variant.

    Z-variants and character locales
    --------------------------------
    Varying stroke count, stroke order or decomposition into character
    components for different I{character locales} is implemented using different
    I{Z-variant}s. For the example given above the entry 这 with 8 strokes is
    given as one Z-variant and the form with 7 strokes is given as another
    Z-variant.

    In most cases one might only be interested in a single visual appearance,
    the "standard" one. This visual appearance would be the one generally used
    in the specific locale.

    Instead of specifying a certain Z-variant most functions will allow for
    passing of a character locale. Giving the locale will apply the default
    Z-variant given by the mapping defined in the database which can be obtained
    by calling L{getDefaultZVariant()}.

    More complex relations as which of several Z-variants for a given character
    are used in a given locale are not covered.

    Kangxi radical functions
    ========================
    Using the Unihan database queries about the Kangxi radical of characters can
    be made.
    It is possible to get a Kangxi radical for a character or lookup all
    characters for a given radical.

    Unicode has extra code points for radical forms (e.g. ⾔), here called
    X{Unicode radical form}s, and radical variant forms (e.g. ⻈), here called
    X{Unicode radical variant}s. These characters should be used when explicitly
    referring to their function as radicals.
    For most of the radicals and variants their exist complementary character
    forms which have the same appearance (e.g. 言 and 讠) and which shall be
    called X{equivalent character}s here.

    Mapping from one to another side is not trivially possible, as some forms
    only exist as radical forms, some only as character forms, but from their
    meaning used in the radical context (called X{isolated radical character}s
    here, e.g. 訁 for Kangxi radical 149).

    Additionally a one to one mapping can't be guaranteed, as some forms have
    two or more equivalent forms in another domain, and mapping is highly
    dependant on the locale.

    CharacterLookup provides methods for dealing with this different kinds of
    characters and the mapping between them.

    X{Character decomposition}
    ==========================
    Many characters can be decomposed into two or more components, that again
    are Chinese characters. This fact can be used in many ways, including
    character lookup, finding patterns for font design or studying characters.
    Even the stroke order and stroke count can be deduced from the stroke
    information of the character's components.

    Character decomposition is highly dependant on the appearance of the
    character, so both I{Z-variant} and I{character locale} need to be clear
    when looking at a decomposition into components.

    More points render this task more complex: decomposition into one set of
    components is not distinct, some characters can be broken down into
    different sets. Furthermore sometimes one component can be given, but the
    other component will not be encoded as a character in its own right.

    These components again might be characters that contain further components
    (again not distinct ones), thus a complex decomposition in several steps is
    possible.

    The basis for the character decomposition lies in the database, where all
    decompositions are stored, using X{Ideographic Description Sequence}s
    (I{IDS}). These sequences consist of Unicode X{IDS operator}s and characters
    to describe the structure of the character. There are
    X{binary IDS operator}s to describe decomposition into two components (e.g.
    ⿰ for one component left, one right as in 好: ⿰女子) or
    X{trinary IDS operator}s for decomposition into three components (e.g. ⿲
    for three components from left to right as in 辨: ⿲⾟刂⾟). Using
    I{IDS operator}s it is possible to give a basic structural information, that
    in many cases is enough for example to derive a overall stroke order from
    two single sets of stroke orders. Further more it is possible to look for
    redundant information in different entries and thus helps to keep the
    definition data clean.

    This class provides methods for retrieving the basic partition entries,
    lookup of characters by components and decomposing as a tree from the
    character as a root down to the X{minimal components} as leaf nodes.

    TODO: Policy about what to classify as partition.

    Strokes
    =======
    Chinese characters consist of different strokes as basic parts. These
    strokes are written in a mostly distinct order called the X{stroke order}
    and have a distinct X{stroke count}.

    The I{stroke order} in the writing of Chinese characters is important e.g.
    for calligraphy or students learning new characters and is normally fixed as
    there is only one possible stroke order for each character. Further more
    there is a fixed set of possible strokes and these strokes carry names.

    As with character decomposition the I{stroke order} and I{stroke count} is
    highly dependant on the appearance of the character, so both I{Z-variant}
    and I{character locale} need to be known.

    Further more the order of strokes can be useful for lookup of characters,
    and so CharacterLookup provides different methods for getting the stroke
    count, stroke order, lookup of stroke names and lookup of characters by
    stroke types and stroke order.

    Most methods work with an abbreviation of stroke names using the first
    letters of each syllable of the Chinese name in Pinyin.

    The I{stroke order} is not always quite clear and even academics fight about
    which order should be considered the correct one, a discussion that
    shouldn't be taking lightly. This circumstance should be considered
    when working with I{stroke order}s.

    TODO: About plans of cjklib how to support different views on the stroke
    order

    TODO: About the different classifications of strokes

    Readings
    ========
    See module L{reading} for a detailed description.

    Character domains
    =================
    Unicode encodes Chinese characters for all languages that make use of them,
    but neither of those writing system make use of the whole spectrum encoded.
    #While it is difficult, if not impossible, to make a clear distinction which
    characters are used in on system and which not, there exist authorative
    character sets that are widely used. Following one of those character sets
    can decrease the amount of characters in question and focus on those
    actually used in the given context.

    In cjklib this concept is implemented as X{Character domain} and if a
    L{CharacterLookup} instance is given a I{Character domain}, then its
    reported results are limited to the characters therein.

    For example limit results to the character encoding BIG5, which encodes
    traditional Chinese characters:
        >>> from cjklib import characterlookup
        >>> cjk = characterlookup.CharacterLookup('T', 'BIG5')

    Available I{character domains} can be checked via
    L{getAvailableCharacterDomains()}. Special character domain C{Unicode}
    represents the whole set of Chinese characters encoded in Unicode.

    @see:
        - Radicals:
            U{http://en.wikipedia.org/wiki/Radical_(Chinese_character)}
        - Z-variants:
            U{http://www.unicode.org/reports/tr38/tr38-5.html#N10211}

    @todo Fix:  Incorporate stroke lookup (bigram) techniques
    @todo Fix:  How to handle character forms (either decomposition or stroke
        order), that can only be found as a component in other characters? We
        already mark them by flagging it with an 'S'.
    @todo Lang: Add option to component decomposition methods to stop on Kangxi
        radical forms without breaking further down beyond those.
    @todo Impl: Further I{character domains} for Japanese, Cantonese, Korean,
        Vietnamese
    """

    CHARARACTER_READING_MAPPING = {'Hangul': ('CharacterHangul', {}),
        'Jyutping': ('CharacterJyutping', {'case': 'lower'}),
        'Pinyin': ('CharacterPinyin', {'toneMarkType': 'Numbers',
            'case': 'lower'})
        }
    """
    A list of readings for which a character mapping exists including the
    database's table name and the reading dialect parameters.

    On conversion the first matching reading will be selected, so supplying
    several equivalent readings has limited use.
    """

    def __init__(self, locale, characterDomain="Unicode", databaseUrl=None,
        dbConnectInst=None):
        """
        Initialises the CharacterLookup.

        If no parameters are given default values are assumed for the connection
        to the database. The database connection parameters can be given in
        databaseUrl, or an instance of L{DatabaseConnector} can be passed in
        dbConnectInst, the latter one being preferred if both are specified.

        @type locale: str
        @param locale: I{character locale} giving the context for glyph and
            radical based functions, one character out of TCJKV.
        @type characterDomain: str
        @param characterDomain: I{character domain} (see
            L{getAvailableCharacterDomains()})
        @type databaseUrl: str
        @param databaseUrl: database connection setting in the format
            C{driver://user:pass@host/database}.
        @type dbConnectInst: instance
        @param dbConnectInst: instance of a L{DatabaseConnector}
        """
        if locale not in set('TCJKV'):
            raise ValueError('Locale not one out of TCJKV: ' + repr(locale))
        else:
            self.locale = locale
        # get connector to database
        if dbConnectInst:
            self.db = dbConnectInst
        else:
            self.db = dbconnector.DatabaseConnector.getDBConnector(databaseUrl)
        # character domain
        domainTable = characterDomain + 'Set'
        if characterDomain == 'Unicode' \
            or self.db.engine.has_table(domainTable):
            # check column
            if characterDomain != 'Unicode':
                self.characterDomainTable = self.db.tables[domainTable]
                if 'ChineseCharacter' not in self.characterDomainTable.columns:
                    raise ValueError(
                        "Character domain table '%s' " % domainTable \
                            + "has no column 'ChineseCharacter'")

            self.characterDomain = characterDomain
        else:
            raise ValueError("Unknown character domain '%s'" % characterDomain)

        self.readingFactory = None

        # test for existing tables that can be used to speed up look up
        self.hasComponentLookup = self.db.engine.has_table('ComponentLookup')
        self.hasStrokeCount = self.db.engine.has_table('StrokeCount')

    def _getReadingFactory(self):
        """
        Gets the L{ReadingFactory} instance.

        @rtype: instance
        @return: a L{ReadingFactory} instance.
        """
        # get reading factory
        if not self.readingFactory:
            self.readingFactory = reading.ReadingFactory(dbConnectInst=self.db)
        return self.readingFactory

    #{ Character domains

    def filterDomainCharacters(self, charList):
        """
        Filters a given list of characters to match only those inside the
        current I{character domain}. Returns the characters in the given order.

        @type charList: list of str
        @param charList: characters to filter
        @rtype: list of str
        @return: list of characters inside the current I{character domain}
        """
        # constrain to selected character domain
        if self.characterDomain == 'Unicode':
            return charList
        else:
            filteredCharList = set(self.db.selectScalars(select(
                [self.characterDomainTable.c.ChineseCharacter],
                self.characterDomainTable.c.ChineseCharacter.in_(charList))))
            # sort
            sortedFiltered = []
            for char in charList:
                if char in filteredCharList:
                    sortedFiltered.append(char)
            return sortedFiltered

    def isCharacterInDomain(self, char):
        """
        Checks if the given character is inside the current character domain.

        @type char: str
        @param char: Chinese character for lookup
        @rtype: bool
        @return: C{True} if character is inside the current character domain,
            C{False} otherwise.
        """
        return char in self.filterDomainCharacters([char])

    def getAvailableCharacterDomains(self):
        """
        Gets a list of all available I{character domains}. By default available
        is domain C{Unicode}, which represents all Chinese characters encoded in
        Unicode. Further domains can be given to the database as tables ending
        in C{...Set} including a column C{ChineseCharacter}, e.g. C{GB2312Set}
        and C{BIG5Set}.

        @rtype: list of str
        @return: list of supported I{character domains}
        """
        domains = ['Unicode']
        for table in self.db.tables:
            if table.endswith('Set') and self.db.engine.has_table(table) \
                and 'ChineseCharacter' in self.db.tables[table].columns:
                domains.append(table[:-3])

        return domains

    #{ Character reading lookup

    def getCharactersForReading(self, readingString, readingN, **options):
        """
        Gets all know characters for the given reading.

        @type readingString: str
        @param readingString: reading string for lookup
        @type readingN: str
        @param readingN: name of reading
        @param options: additional options for handling the reading input
        @rtype: list of str
        @return: list of characters for the given reading
        @raise UnsupportedError: if no mapping between characters and target
            reading exists. Either the database wasn't build with the table
            needed or the given reading cannot be converted to any of the
            available mappings.
        @raise ConversionError: if conversion from the internal source reading
            to the given target reading fails.
        """
        # check for available mapping from Chinese characters to a compatible
        #   reading
        compatReading = self._getCompatibleCharacterReading(readingN)
        tableName, compatOptions \
            = self.CHARARACTER_READING_MAPPING[compatReading]

        # translate reading form to target reading, for readingN=compatReading
        #   get standard form if supported
        readingFactory = self._getReadingFactory()
        if readingN != compatReading \
            or readingFactory.isReadingConversionSupported(readingN, readingN):
            readingString = readingFactory.convert(readingString, readingN,
                compatReading, sourceOptions=options,
                targetOptions=compatOptions)

        # lookup characters
        table = self.db.tables[tableName]

        # constrain to selected character domain
        if self.characterDomain == 'Unicode':
            fromObj = []
        else:
            fromObj = [table.join(self.characterDomainTable,
                table.c.ChineseCharacter \
                    == self.characterDomainTable.c.ChineseCharacter)]

        return self.db.selectScalars(select([table.c.ChineseCharacter],
            table.c.Reading==readingString,
            from_obj=fromObj).order_by(table.c.ChineseCharacter))

    def getReadingForCharacter(self, char, readingN, **options):
        """
        Gets all know readings for the character in the given target reading.

        @type char: str
        @param char: Chinese character for lookup
        @type readingN: str
        @param readingN: name of target reading
        @param options: additional options for handling the reading output
        @rtype: str
        @return: list of readings for the given character
        @raise UnsupportedError: if no mapping between characters and target
            reading exists.
        @raise ConversionError: if conversion from the internal source reading
            to the given target reading fails.
        """
        # check for available mapping from Chinese characters to a compatible
        # reading
        compatReading = self._getCompatibleCharacterReading(readingN, False)
        tableName, compatOptions \
            = self.CHARARACTER_READING_MAPPING[compatReading]
        readingFactory = self._getReadingFactory()

        # lookup readings
        table = self.db.tables[tableName]
        readings = self.db.selectScalars(select([table.c.Reading],
            table.c.ChineseCharacter==char).order_by(table.c.Reading))

        # check if we need to convert reading
        if compatReading != readingN \
            or readingFactory.isReadingConversionSupported(readingN, readingN):
            # translate reading forms to target reading, for
            #   readingN=characterReading get standard form if supported
            transReadings = []
            for readingString in readings:
                readingString = readingFactory.convert(readingString,
                    compatReading, readingN, sourceOptions=compatOptions,
                    targetOptions=options)
                if readingString not in transReadings:
                    transReadings.append(readingString)
            return transReadings
        else:
            return readings

    def hasMappingForCharacterToReading(self, readingN):
        """
        Returns C{True} if a mapping between Chinese characters and the given
        I{reading} is supported.

        @type readingN: str
        @param readingN: name of reading
        @rtype: bool
        @return: C{True} if a mapping between Chinese characters and the given
            I{reading} is supported, C{False} otherwise.
        """
        try:
            self._getCompatibleCharacterReading(readingN, toCharReading=True)
            return True
        except exception.UnsupportedError:
            return False

    def hasMappingForReadingToCharacter(self, readingN):
        """
        Returns C{True} if a mapping between the given I{reading} and Chinese
        characters is supported.

        @type readingN: str
        @param readingN: name of reading
        @rtype: bool
        @return:C{True} if a mapping between the given I{reading} and Chinese
            characters is supported, C{False} otherwise.
        """
        try:
            self._getCompatibleCharacterReading(readingN, toCharReading=False)
            return True
        except exception.UnsupportedError:
            return False

    def _getCompatibleCharacterReading(self, readingN, toCharReading=True):
        """
        Gets a reading where a mapping from to Chinese characters is supported
        and that is compatible (a conversion is supported) to the given reading.

        @type readingN: str
        @param readingN: name of reading
        @type toCharReading: bool
        @param toCharReading: C{True} if conversion is done in direction to the
            given reading, C{False} otherwise
        @rtype: str
        @return: a reading that is compatible to the given one and where
            character lookup is supported
        @raise UnsupportedError: if no mapping between characters and target
            reading exists.
        """
        # iterate all available char-reading mappings to find a compatible
        # reading
        for characterReading in self.CHARARACTER_READING_MAPPING:
            # check first if database has the table in need
            table, _ = self.CHARARACTER_READING_MAPPING[characterReading]
            if not self.db.engine.has_table(table):
                continue

            if readingN == characterReading:
                return characterReading
            else:
                if toCharReading:
                    if self._getReadingFactory().isReadingConversionSupported(
                        readingN, characterReading):
                        return characterReading
                else:
                    if self._getReadingFactory().isReadingConversionSupported(
                        characterReading, readingN):
                        return characterReading
        if toCharReading:
            raise exception.UnsupportedError(
                "No mapping from characters to reading '%s'" % readingN)
        else:
            raise exception.UnsupportedError(
                "No mapping from reading '%s' to characterss" % readingN)

    #}

    def _locale(self, locale):
        """
        Gets the locale search value for a database lookup on databases with
        I{character locale} dependant content.

        @type locale: str
        @param locale: I{character locale} (one out of TCJKV)
        @rtype: str
        @return: search locale used for SQL select
        @raise ValueError: if invalid I{character locale} specified
        @todo Fix: This probably requires a full table scan
        """
        locale = locale.upper()
        if not locale in set('TCJKV'):
            raise ValueError("'" + locale + "' is not a valid character locale")
        return '%' + locale + '%'

    #{ Character variant lookup

    def getCharacterVariants(self, char, variantType):
        u"""
        Gets the variant forms of the given type for the character.

        The type can be one out of:
            - C, I{compatible character} form (if character was added to Unicode
                to maintain compatibility and round-trip convertibility)
            - M, I{semantic variant} forms, which are often used interchangeably
                instead of the character.
            - P, I{specialised semantic variant} forms, which are often used
                interchangeably instead of the character but limited to certain
                contexts.
            - Z, I{Z-variant} forms, which only differ in typeface (and would
                have been unified if not to maintain round trip convertibility)
            - S, I{simplified Chinese character} forms, originating from the
                character simplification process of the PR China.
            - T, I{traditional character} forms for a
                I{simplified Chinese character}.

        Variants depend on the locale which is not taken into account here. Thus
        some of the returned characters might be only be variants under some
        locales.

        @type char: str
        @param char: Chinese character
        @type variantType: str
        @param variantType: type of variant(s) to be returned
        @rtype: list of str
        @return: list of character variant(s) of given type

        @todo Docu: Write about different kinds of variants
        @todo Impl: Give a source on variant information as information can
            contradict itself
            (U{http://www.unicode.org/reports/tr38/tr38-5.html#N10211}). See
            呆 (U+5446) which has one form each for semantic and specialised
            semantic, each derived from a different source. Change also in
            L{getAllCharacterVariants()}.
        @todo Lang: What is the difference on Z-variants and
            compatible variants? Some links between two characters are
            bidirectional, some not. Is there any rule?
        """
        variantType = variantType.upper()
        if not variantType in set('CMPZST'):
            raise ValueError("'" + variantType \
                + "' is not a valid variant type")

        table = self.db.tables['CharacterVariant']
        # constrain to selected character domain
        if self.characterDomain == 'Unicode':
            fromObj = []
        else:
            fromObj = [table.join(self.characterDomainTable, table.c.Variant \
                == self.characterDomainTable.c.ChineseCharacter)]

        return self.db.selectScalars(select([table.c.Variant],
            and_(table.c.ChineseCharacter == char,
                table.c.Type == variantType),
            from_obj=fromObj).order_by(table.c.Variant))

    def getAllCharacterVariants(self, char):
        """
        Gets all variant forms regardless of the type for the character.

        A list of tuples is returned, including the character and its variant
        type. See L{getCharacterVariants()} for variant types.

        Variants depend on the locale which is not taken into account here. Thus
        some of the returned characters might be only be variants under some
        locales.

        @type char: str
        @param char: Chinese character
        @rtype: list of tuple
        @return: list of character variant(s) with their type
        """
        table = self.db.tables['CharacterVariant']
        # constrain to selected character domain
        if self.characterDomain == 'Unicode':
            fromObj = []
        else:
            fromObj = [table.join(self.characterDomainTable, table.c.Variant \
                == self.characterDomainTable.c.ChineseCharacter)]

        return self.db.selectRows(select([table.c.Variant, table.c.Type],
            table.c.ChineseCharacter == char,
            from_obj=fromObj).order_by(table.c.Variant))

    def getDefaultZVariant(self, char):
        """
        Gets the default Z-variant for the given character under the chosen
        I{character locale}.

        The Z-variant returned is an index to the internal database of different
        character glyphs and represents the most common glyph used under the
        given locale.

        @type char: str
        @param char: Chinese character
        @rtype: int
        @return: Z-variant
        @raise NoInformationError: if no Z-variant information is available
        """
        return self.getLocaleDefaultZVariant(char, self.locale)

    def getLocaleDefaultZVariant(self, char, locale):
        """
        Gets the default Z-variant for the given character under the given
        locale.

        The Z-variant returned is an index to the internal database of different
        character glyphs and represents the most common glyph used under the
        given locale.

        @type char: str
        @param char: Chinese character
        @type locale: str
        @param locale: I{character locale} (one out of TCJKV)
        @rtype: int
        @return: Z-variant
        @raise NoInformationError: if no Z-variant information is available
        @raise ValueError: if invalid I{character locale} specified
        """
        table = self.db.tables['LocaleCharacterVariant']
        zVariant = self.db.selectScalar(select([table.c.ZVariant],
            and_(table.c.ChineseCharacter == char,
                table.c.Locale.like(self._locale(locale))))\
            .order_by(table.c.ZVariant))

        if zVariant != None:
            return zVariant
        else:
            # if no entry given, assume default
            return self.getCharacterZVariants(char)[0]

    def getCharacterZVariants(self, char):
        """
        Gets a list of character Z-variant indices (glyphs) supported by the
        database.

        A Z-variant index specifies a particular character glyph which is needed
        by several glyph-dependant methods instead of the abstract character
        defined by Unicode.

        @type char: str
        @param char: Chinese character
        @rtype: list of int
        @return: list of supported Z-variants
        @raise NoInformationError: if no Z-variant information is available
        """
        # return all known variant indices, order to be deterministic
        table = self.db.tables['ZVariants']
        result = self.db.selectScalars(select([table.c.ZVariant],
            table.c.ChineseCharacter == char).order_by(table.c.ZVariant))
        if not result:
            raise exception.NoInformationError(
                "No Z-variant information available for '" + char + "'")

        return result

    #}
    #{ Character stroke functions

    def getStrokeCount(self, char, zVariant=None):
        """
        Gets the stroke count for the given character.

        @type char: str
        @param char: Chinese character
        @type zVariant: int
        @param zVariant: I{Z-variant} of the first character. This parameter is
            optional and if omitted the default I{Z-variant} defined by
            L{getDefaultZVariant()} will be used.
        @rtype: int
        @return: stroke count of given character
        @raise NoInformationError: if no stroke count information available
        @raise ValueError: if an invalid I{character locale} is specified
        @attention: The quality of the returned data depends on the sources used
            when compiling the database. Unihan itself only gives very general
            stroke order information without being bound to a specific glyph.
        """
        if zVariant == None:
            zVariant = self.getDefaultZVariant(char)

        # if table exists use it
        if self.hasStrokeCount:
            table = self.db.tables['StrokeCount']
            result = self.db.selectScalar(select([table.c.StrokeCount],
                and_(table.c.ChineseCharacter == char,
                    table.c.ZVariant == zVariant)))
            if not result:
                raise exception.NoInformationError(
                    "Character has no stroke count information")
            return result
        else:
            # use incomplete way with using the stroke order (there might be
            #   less stroke order entries than stroke count entries)
            try:
                return len(self.getStrokeOrder(char, zVariant=zVariant))
            except exception.NoInformationError:
                raise exception.NoInformationError(
                    "Character has no stroke count information")

    def getStrokeCountDict(self):
        """
        Gets the stroke count table from the database for all characters in the
        chosen I{character domain}.

        @rtype: dict
        @return: dictionary of key pair character, Z-variant and value stroke
            count
        @attention: The quality of the returned data depends on the sources used
            when compiling the database. Unihan itself only gives very general
            stroke order information without being bound to a specific glyph.
        """
        table = self.db.tables['StrokeCount']
        # constrain to selected character domain
        if self.characterDomain == 'Unicode':
            fromObj = []
        else:
            fromObj = [table.join(self.characterDomainTable,
                table.c.ChineseCharacter \
                    == self.characterDomainTable.c.ChineseCharacter)]

        result = self.db.selectRows(select(
            [table.c.ChineseCharacter, table.c.ZVariant, table.c.StrokeCount],
            from_obj=fromObj))
        return dict([((char, zVariant), strokeCount) \
            for char, zVariant, strokeCount in result])

    #_strokeIndexLookup = {}
    #"""A dictionary containing the stroke indices for a set index length."""
    #def getStrokeIndexLookup(self, indexLength):
        #"""
        #Gets a stroke lookup table for the given index length and assigns each
        #stroke taken into account with an unique index.

        #The first M{indexLength-1} most frequent strokes are taken into account,
        #all other strokes are rejected from the index.

        #@type indexLength: int
        #@param indexLength: length of the index
        #@rtype: dict
        #@return: dictionary for performing stroke lookups
        #"""
        #if not self._strokeIndexLookup.has_key(indexLength):
            #strokeTable = self.db.selectSoleValue('StrokeFrequency',
                #'Stroke', orderBy = ['Frequency'], orderDescending=True,
                #limit = indexLength)
            #counter = 0
            #strokeIndexLookup = {}
            ## put all stroke abbreviations of stroke from strokeTable into dict
            #for stroke in strokeTable:
                #strokeIndexLookup[stroke] = counter
                #counter = counter + 1
            #self._strokeIndexLookup[indexLength] = strokeIndexLookup
        #return self._strokeIndexLookup[indexLength]

    #def _getStrokeBitField(self, strokeSet, bitLength=30):
        #"""
        #Gets the bigram bit field for the given stroke set.

        #The first M{bitLength-1} strokes are assigned to one bit position, all
        #other strokes are assigned to position M{bitLength}. Bits for strokes
        #present are set to 1 all others to 0.

        #@type strokeSet: list of str
        #@param strokeSet: set of stroke types
        #@type bitLength: int
        #@param bitLength: length of the bit field
        #@rtype: int
        #@return: bit field with bits for present strokes set to 1
        #"""
        #strokeIndexLookup = self.getStrokeIndexLookup(bitLength-1)
        ## now build bit field
        #bitField = 0
        #for strokeAbbrev in strokeSet:
            #stroke = self.getStrokeForAbbrev(strokeAbbrev)
            #if strokeIndexLookup.has_key(stroke):
                #index = strokeIndexLookup[stroke]
            #else:
                #index = bitLength
            #bitField = bitField | int(math.pow(2, index))
        #return bitField

    #_bigramIndexLookup = {}
    #"""A dictionary containing the bigram indices for a set bigram index
        #length."""
    #def _getBigramIndexLookup(self, indexLength):
        #"""
        #Gets a bigram lookup table for the given index length and assigns each
        #bigram taken into account with an unique index.

        #The first M{indexLength-1} most frequent bigrams are taken into account,
        #all other bigrams are rejected from the index.

        #@type indexLength: int
        #@param indexLength: length of the index
        #@rtype: dict
        #@return: dictionary for performing bigram lookups
        #"""
        #if not self._bigramIndexLookup.has_key(indexLength):
            #counter = 0
            #bigramIndexLookup = {}
            ## put all stroke abbreviations of stroke from strokeTable into dict
            #bigramTable = self.db.selectSoleValue('StrokeBigramFrequency',
                #'StrokeBigram', orderBy = ['Frequency'], orderDescending = True,
                #limit = indexLength)
            #for bigram in bigramTable:
                #bigramIndexLookup[bigram] = counter
                #counter = counter + 1
            #self._bigramIndexLookup[indexLength] = bigramIndexLookup
        #return self._bigramIndexLookup[indexLength]

    #def _getBigramBitField(self, strokeList, bitLength=30):
        #"""
        #Gets the bigram bit field for the given list of strokes.

        #The first M{bitLength-1} bigrams are assigned to one bit position, all
        #other bigrams are assigned to position M{bitLength}. Bits for bigrams
        #present are set to 1 all others to 0.

        #@type strokeList: list of str
        #@param strokeList: list of stroke
        #@type bitLength: int
        #@param bitLength: length of the bit field
        #@rtype: int
        #@return: bit field with bits for present bigrams set to 1
        #"""
        #bigramIndexLookup = self._getBigramIndexLookup(bitLength-1)
        ## now build bit field
        #bitField = 0
        #lastStroke = self.getStrokeForAbbrev(strokeList[0])
        #for strokeAbbrev in strokeList[1:]:
            #stroke = self.getStrokeForAbbrev(strokeAbbrev)
            #if bigramIndexLookup.has_key(lastStroke+stroke):
                #index = bigramIndexLookup[lastStroke+stroke]
            #else:
                #index = bitLength
            #bitField = bitField | int(math.pow(2, index))
        #return bitField

    #def getStrokeOrderDistance(self, strokeOrderListA, strokeOrderListB,
        #substitutionPenalty=1, insertionPenalty=1.5, deletionPenalty=1.5):
        #"""
        #Calculates the Levenshtein distance for the two given stroke orders.
 
        #Stroke are given as abbreviated form.

        #@type strokeOrderListA: list of str
        #@param strokeOrderListA: strokes A ordered in list form
        #@type strokeOrderListB: list of str
        #@param strokeOrderListB: strokes B ordered in list form
        #@type substitutionPenalty: float
        #@param substitutionPenalty: penalty for substituting elements
        #@type insertionPenalty: float
        #@param insertionPenalty: penalty for inserting elements
        #@type deletionPenalty: float
        #@param deletionPenalty: penalty for deleting elements
        #@rtype: float
        #@return: Levenshtein distance of both stroke orders
        #"""
        #n = len(strokeOrderListA)
        #m = len(strokeOrderListB)
        #d = [[0 for i in range(0, n+1)]
            #for j in range(0, m+1)]
        #for i in range(0, n+1):
            #d[0][i] = i
        #for j in range(0, m+1):
            #d[j][0] = j
        #for i in range(1, n+1):
            #for j in range(1, m+1):
                #if strokeOrderListA[i-1] == strokeOrderListB[j-1]:
                    #subst = 0
                #else:
                    #subst = substitutionPenalty
                #d[j][i] = min(d[j-1][i-1] + subst,               # substitution
                              #d[j][i-1] + insertionPenalty,      # insertion
                              #d[j-1][i] + deletionPenalty)       # deletion
        #return d[m][n]

    #def getCharactersForStrokes(self, strokeList, locale):
        #"""
        #Gets all characters for the given list of stroke types.
 
        #Stroke types are given as abbreviated form.

        #@type strokeList: list of str
        #@param strokeList: list of stroke types
        #@type locale: str
        #@param locale: I{character locale} (one out of TCJKV)
        #@rtype: list of tuple
        #@return: list of character, Z-variant pairs having the same stroke types
        #@raise ValueError: if an invalid I{character locale} is specified
        #"""
        #return self.db.select('StrokeBitField',
            #['ChineseCharacter', 'ZVariant'],
           # {'StrokeField': self._getStrokeBitField(strokeList),
            #'Locale': self._locale(locale)},
            #orderBy = ['ChineseCharacter'])

    #def getCharactersForStrokeOrder(self, strokeOrder, locale):
        #"""
        #Gets all characters for the given stroke order.
 
        #Strokes are given as abbreviated form and can be separated by a
        #space or a hyphen.

        #@type strokeOrder: str
        #@param strokeOrder: stroke order consisting of stroke abbreviations
            #separated by a space or hyphen
        #@type locale: str
        #@param locale: I{character locale} (one out of TCJKV)
        #@rtype: list of tuple
        #@return: list of character, Z-variant pairs
        #@raise ValueError: if an invalid I{character locale} is specified
        #@bug:  Table 'strokebitfield' doesn't seem to include entries from
            #'strokeorder' but only from character decomposition table:

            #>>> print ",".join([a for a,b in cjk.getCharactersForStrokes(['S','H','HZ'], 'C')])
            #亘,卓,占,古,叶,吉,吐,吕,咕,咭,哇,哩,唱,啡,坦,坫,垣,埋,旦,旧,早,旰,旱,旺,昌,玷,理,田,畦,眭,罟,罡,罩,罪,量,靼,鞋

        #@bug:  Character lookup from stroke order seems to be broken. 皿 is in
            #database but wouldn't be found::
                #./cjknife -o S-HZ-S-S-H
                #田旦占
        #"""
        #strokeList = strokeOrder.replace(' ', '-').split('-')

        #results = self.db.select(['StrokeBitField s', 'BigramBitField b',
            #'StrokeCount c'], ['s.ChineseCharacter', 's.ZVariant'],
           # {'s.Locale': '=b.Locale', 's.Locale': '=c.Locale',
            #'s.ChineseCharacter': '=b.ChineseCharacter',
            #'s.ChineseCharacter': '=c.ChineseCharacter',
            #'s.ZVariant': '=b.ZVariant', 's.ZVariant': '=c.ZVariant',
            #'s.Locale': self._locale(locale),
            #'s.StrokeField': self._getStrokeBitField(strokeList),
            #'b.BigramField': self._getBigramBitField(strokeList),
            #'c.StrokeCount': len(strokeList)})
        #resultList = []
        ## check exact match of stroke order for all possible matches
        #for char, zVariant in results:
            #so = self.getStrokeOrderAbbrev(char, locale, zVariant)
            #soList = so.replace(' ', '-').split('-')
            #if soList == strokeList:
                #resultList.append((char, zVariant))
        #return resultList

    #def getCharactersForStrokeOrderFuzzy(self, strokeOrder, locale, minEstimate,
        #strokeCountVariance=2, strokeVariance=2, bigramVariance=3):
        #"""
        #Gets all characters for the given stroke order reaching the minimum
        #estimate using a fuzzy search as to allowing fault-tolerant searches.
 
        #Strokes are given as abbreviated form and can be separated by a
        #space or a hyphen.

        #The search is commited by looking for equal stroke count, equal stroke
        #types and stroke bigrams (following pairs of strokes). Specifying
        #C{strokeCountVariance} for allowing variance in stroke count,
        #C{strokeVariance} for variance in stroke occurrences (for frequent ones)
        #and C{bigramVariance} for variance in frequent stroke bigrams can adapt
        #query to fit needs of minimum estimate. Allowing less variances will
        #result in faster queries but lesser results, thus possibly omiting good
        #matches.

        #An estimate on the first search results is calculated and only entries
        #reaching over the specified minimum estimate are included in the output.

        #@type strokeOrder: str
        #@param strokeOrder: stroke order consisting of stroke abbreviations
            #separated by a space or hyphen
        #@type locale: str
        #@param locale: I{character locale} (one out of TCJKV)
        #@type minEstimate: int
        #@param minEstimate: minimum estimate that entries in output have to
            #reach
        #@type strokeCountVariance: int
        #@param strokeCountVariance: variance of stroke count
        #@type strokeVariance: int
        #@param strokeVariance: variance of stroke types
        #@type bigramVariance: int
        #@param bigramVariance: variance of stroke bigrams
        #@rtype: list of tuple
        #@return: list of character, Z-variant pairs
        #@raise ValueError: if an invalid I{character locale} is specified
        #"""
        #strokeList = strokeOrder.replace(' ', '-').split('-')
        #strokeCount = len(strokeList)
        #strokeBitField = self._getStrokeBitField(strokeList)
        #bigramBitField = self._getBigramBitField(strokeList)
        #results = self.db.select(['StrokeBitField s', 'BigramBitField b',
            #'StrokeCount c'], ['s.ChineseCharacter', 's.ZVariant'],
           # {'s.Locale': '=b.Locale', 's.Locale': '=c.Locale',
            #'s.ChineseCharacter': '=b.ChineseCharacter',
            #'s.ChineseCharacter': '=c.ChineseCharacter',
            #'s.ZVariant': '=b.ZVariant', 's.ZVariant': '=c.ZVariant',
            #'s.Locale': self._locale(locale),
            #'bit_count(s.StrokeField ^ ' + str(strokeBitField) + ')':
            #'<=' + str(strokeVariance),
            #'bit_count(b.BigramField ^ ' + str(bigramBitField) + ')':
            #'<=' + str(bigramVariance),
            #'c.StrokeCount': '>=' + str(strokeCount-strokeCountVariance),
            #'c.StrokeCount': '<=' + str(strokeCount+strokeCountVariance)},
            #distinctValues=True)
        #resultList = []
        #for char, zVariant in results:
            #so = self.getStrokeOrderAbbrev(char, locale, zVariant)
            #soList = so.replace(' ', '-').split('-')
            #estimate = 1.0 / \
                #(math.sqrt(1.0 + (8*float(self.getStrokeOrderDistance(
                    #strokeList, soList)) / strokeCount)))
            #if estimate >= minEstimate:
                #resultList.append((char, zVariant, estimate))
        #return resultList

    _strokeLookup = None
    """A dictionary containing stroke forms for stroke abbreviations."""
    def getStrokeForAbbrev(self, abbrev):
        """
        Gets the stroke form for the given abbreviated name (e.g. 'HZ').

        @type abbrev: str
        @param abbrev: abbreviated stroke name
        @rtype: str
        @return: Unicode stroke character
        @raise ValueError: if invalid stroke abbreviation is specified
        """
        # build stroke lookup table for the first time
        if not self._strokeLookup:
            self._strokeLookup = {}
            table = self.db.tables['Strokes']
            result = self.db.selectRows(select(
                [table.c.Stroke, table.c.StrokeAbbrev]))
            for stroke, strokeAbbrev in result:
                self._strokeLookup[strokeAbbrev] = stroke
        if self._strokeLookup.has_key(abbrev):
            return self._strokeLookup[abbrev]
        else:
            raise ValueError(abbrev + " is no valid stroke abbreviation")

    def getStrokeForName(self, name):
        u"""
        Gets the stroke form for the given name (e.g. '横折').

        @type name: str
        @param name: Chinese name of stroke
        @rtype: str
        @return: Unicode stroke char
        @raise ValueError: if invalid stroke name is specified
        """
        table = self.db.tables['Strokes']
        stroke = self.db.selectScalar(select([table.c.Stroke],
            table.c.Name == name))
        if stroke:
            return stroke
        else:
            raise ValueError(name + " is no valid stroke name")

    def getStrokeOrder(self, char, zVariant=None):
        """
        Gets the stroke order sequence for the given character.

        The stroke order is constructed using the character decomposition into
        components.

        @type char: str
        @param char: Chinese character
        @type zVariant: int
        @param zVariant: I{Z-variant} of the first character. This parameter is
            optional and if omitted the default I{Z-variant} defined by
            L{getDefaultZVariant()} will be used.
        @rtype: list
        @return: list of Unicode strokes
        @raise NoInformationError: if no stroke order information available
        """
        strokeOrderAbbrev = self.getStrokeOrderAbbrev(char, zVariant)
        strokeOrder = []
        for stroke in strokeOrderAbbrev.replace(' ', '-').split('-'):
            strokeOrder.append(self.getStrokeForAbbrev(stroke))
        return strokeOrder

    def getStrokeOrderAbbrev(self, char, zVariant=None):
        """
        Gets the stroke order sequence for the given character as a string of
        stroke abbreviated names separated by spaces and hyphens.

        The stroke order is constructed using the character decomposition into
        components.

        @type char: str
        @param char: Chinese character
        @type zVariant: int
        @param zVariant: I{Z-variant} of the first character. This parameter is
            optional and if omitted the default I{Z-variant} defined by
            L{getDefaultZVariant()} will be used.
        @rtype: str
        @return: string of stroke abbreviations separated by spaces and hyphens.
        @raise NoInformationError: if no stroke order information available
        @todo Lang: Add stroke order source to stroke order data so that in
            general different and contradicting stroke order information can be
            given. The user then could prefer several sources that in the order
            given would be queried.
        """
        def getStrokeOrderEntry(char, zVariant):
            """
            Gets the stroke order sequence for the given character from the
            database's stroke order lookup table.

            @type char: str
            @param char: Chinese character
            @type zVariant: int
            @param zVariant: I{Z-variant} of the first character
            @rtype: str
            @return: string of stroke abbreviations separated by spaces and
                hyphens.
            @raise NoInformationError: if no stroke order information available
            @raise ValueError: if an invalid I{character locale} is specified
            """
            table = self.db.tables['StrokeOrder']
            result = self.db.selectScalar(select([table.c.StrokeOrder],
                and_(table.c.ChineseCharacter == char,
                    table.c.ZVariant == zVariant), distinct=True))
            if not result:
                raise exception.NoInformationError(
                    "Character has no stroke order information")
            return result

        def getFromDecomposition(decompositionTreeList):
            """
            Gets stroke order from the tree of a single partition entry.

            @type decompositionTreeList: list
            @param decompositionTreeList: list of decomposition trees to derive
                the stroke order from
            @rtype: str
            @return: string of stroke abbreviations separated by spaces and
                hyphens.
            @raise NoInformationError: if no stroke order information available
            """

            def getFromEntry(subTree, index=0):
                """
                Goes through a single layer of a tree recursively.

                @type subTree: list
                @param subTree: decomposition tree to derive the stroke order
                    from
                @type index: int
                @param index: index of current layer
                @rtype: str
                @return: string of stroke abbreviations separated by spaces and
                    hyphens.
                @raise NoInformationError: if no stroke order information
                    available
                """
                strokeOrder = []
                if type(subTree[index]) != type(()):
                    # IDS operator
                    character = subTree[index]
                    if self.isBinaryIDSOperator(character):
                        # check for IDS operators we can't make any order
                        # assumption about
                        if character in [u'⿴', u'⿻']:
                            raise exception.NoInformationError(
                                "Character has no stroke order information")
                        else:
                            if character in [u'⿺', u'⿶']:
                                # IDS operators with order right one first
                                subSequence = [1, 0]
                            else:
                                # IDS operators with order left one first
                                subSequence = [0, 1]
                            # Get stroke order for both components
                            subStrokeOrder = []
                            for i in range(0,2):
                                so, index = getFromEntry(subTree, index+1)
                                subStrokeOrder.append(so)
                            # Append in proper order
                            for seq in subSequence:
                                strokeOrder.append(subStrokeOrder[seq])
                    elif self.isTrinaryIDSOperator(character):
                        # Get stroke order for three components
                        for i in range(0,3):
                            so, index = getFromEntry(subTree, index+1)
                            strokeOrder.append(so)
                else:
                    # no IDS operator but character
                    char, charZVariant, componentTree = subTree[index]
                    # if the character is unknown or there is none raise
                    if char == u'？':
                        raise exception.NoInformationError(
                            "Character has no stroke order information")
                    else:
                        # check if we have a stroke order entry first
                        so = getStrokeOrderEntry(char, charZVariant)
                        if not so:
                            # no entry, so get from partition
                            so = getFromDecomposition(componentTree)
                        strokeOrder.append(so)
                return (' '.join(strokeOrder), index)

            # Try to find a partition without unknown components, if more than
            # one partition is given (take the one with maximum entry length).
            # This ensures we will have a full stroke order if at least one
            # partition is complete. This is important as the database will
            # never be complete.
            strokeOrder = ''
            for decomposition in decompositionTreeList:
                try:
                    so, i = getFromEntry(decomposition)
                    if len(so) >= len(strokeOrder):
                        strokeOrder = so
                except exception.NoInformationError:
                    pass
            if not strokeOrder:
                raise exception.NoInformationError(
                    "Character has no stroke order information")
            return strokeOrder

        if zVariant == None:
            zVariant = self.getDefaultZVariant(char)
        # if there is an entry for the whole character return it
        try:
            strokeOrder = getStrokeOrderEntry(char, zVariant)
            return strokeOrder
        except exception.NoInformationError:
            pass
        # try to decompose character into components and build stroke order
        decompositionTreeList = self.getDecompositionTreeList(char,
            zVariant=zVariant)
        strokeOrder = getFromDecomposition(decompositionTreeList)
        return strokeOrder

    #}
    #{ Character radical functions

    def getCharacterKangxiRadicalIndex(self, char):
        """
        Gets the Kangxi radical index for the given character as defined by the
        I{Unihan} database.

        @type char: str
        @param char: Chinese character
        @rtype: int
        @return: Kangxi radical index
        @raise NoInformationError: if no Kangxi radical index information for
            given character
        """
        table = self.db.tables['CharacterKangxiRadical']
        result = self.db.selectScalar(select([table.c.RadicalIndex],
            table.c.ChineseCharacter == char))
        if not result:
            raise exception.NoInformationError(
                "Character has no Kangxi radical information")
        return result

    def getCharacterKangxiRadicalResidualStrokeCount(self, char, zVariant=None):
        u"""
        Gets the Kangxi radical form (either a I{Unicode radical form} or a
        I{Unicode radical variant}) found as a component in the character and
        the stroke count of the residual character components.

        The representation of the included radical or radical variant form
        depends on the respective character variant and thus the form's
        Z-variant is returned. Some characters include the given radical more
        than once and in some cases the representation is different between
        those same forms thus in the general case several matches can be
        returned each entry with a different radical form Z-variant. In these
        cases the entries are sorted by their Z-variant.

        There are characters which include both, the radical form and a variant
        form of the radical (e.g. 伦: 人 and 亻). In these cases both are
        returned.

        This method will return radical forms regardless of the selected locale,
        e.g. radical ⻔ is returned for character 间, though this variant form is
        not recognised under a traditional locale (like the character itself).

        @type char: str
        @param char: Chinese character
        @type zVariant: int
        @param zVariant: I{Z-variant} of the first character. This parameter is
            optional and if omitted the default I{Z-variant} defined by
            L{getDefaultZVariant()} will be used.
        @rtype: list of tuple
        @return: list of radical/variant form, its Z-variant, the main layout of
            the character (using a I{IDS operator}), the position of the radical
            wrt. layout (0, 1 or 2) and the residual stroke count.
        @raise NoInformationError: if no stroke count information available
        @raise ValueError: if an invalid I{character locale} is specified
        """
        radicalIndex = self.getCharacterKangxiRadicalIndex(char)
        entries = self.getCharacterRadicalResidualStrokeCount(char,
            radicalIndex, zVariant)
        if entries:
            return entries
        else:
            raise exception.NoInformationError(
                "Character has no radical form information")

    def getCharacterRadicalResidualStrokeCount(self, char, radicalIndex,
        zVariant=None):
        u"""
        Gets the radical form (either a I{Unicode radical form} or a
        I{Unicode radical variant}) found as a component in the character and
        the stroke count of the residual character components.

        This is a more general version of
        L{getCharacterKangxiRadicalResidualStrokeCount()} which is not limited
        to the mapping of characters to a Kangxi radical as done by Unihan.

        @type char: str
        @param char: Chinese character
        @type radicalIndex: int
        @param radicalIndex: radical index
        @type zVariant: int
        @param zVariant: I{Z-variant} of the first character. This parameter is
            optional and if omitted the default I{Z-variant} defined by
            L{getDefaultZVariant()} will be used.
        @rtype: list of tuple
        @return: list of radical/variant form, its Z-variant, the main layout of
            the character (using a I{IDS operator}), the position of the radical
            wrt. layout (0, 1 or 2) and the residual stroke count.
        @raise NoInformationError: if no stroke count information available
        @raise ValueError: if an invalid I{character locale} is specified
        @todo Lang: Clarify on characters classified under a given radical
            but without any proper radical glyph found as component.
        @todo Lang: Clarify on different radical zVariants for the same radical
            form. At best this method should return one and only one radical
            form (glyph).
        @todo Impl: Give the I{Unicode radical form} and not the equivalent
            character form in the relevant table as to always return the pure
            radical form (also avoids duplicates). Then state:

            If the included component has an appropriate I{Unicode radical form}
            or I{Unicode radical variant}, then this form is returned. In either
            case the radical form can be an ordinary character.
        """
        if zVariant == None:
            zVariant = self.getDefaultZVariant(char)
        table = self.db.tables['CharacterRadicalResidualStrokeCount']
        entries = self.db.selectRows(select([table.c.RadicalForm,
                table.c.RadicalZVariant, table.c.MainCharacterLayout,
                table.c.RadicalRelativePosition, table.c.ResidualStrokeCount],
            and_(table.c.ChineseCharacter == char, table.c.ZVariant == zVariant,
            table.c.RadicalIndex == radicalIndex)).order_by(
                table.c.ResidualStrokeCount, table.c.RadicalZVariant,
                table.c.RadicalForm, table.c.MainCharacterLayout,
                table.c.RadicalRelativePosition))
        # add key columns to sort order to make return value deterministic
        if entries:
            return entries
        else:
            raise exception.NoInformationError(
                "Character has no radical form information")

    def getCharacterRadicalResidualStrokeCountDict(self):
        u"""
        Gets the full table of radical forms (either a I{Unicode radical form}
        or a I{Unicode radical variant}) found as a component in the character
        and the stroke count of the residual character components from the
        database.

        A typical entry looks like
        C{(u'众', 0): {9: [(u'人', 0, u'⿱', 0, 4), (u'人', 0, u'⿻', 0, 4)]}},
        and can be accessed as C{radicalDict[(u'众', 0)][9]} with the Chinese
        character, its Z-variant and Kangxi radical index. The values are given
        in the order I{radical form}, I{radical Z-variant}, I{character layout},
        I{relative position of the radical} and finally the
        I{residual stroke count}.

        @rtype: dict
        @return: dictionary of radical/residual stroke count entries.
        """
        radicalDict = {}
        # get entries from database
        table = self.db.tables['CharacterRadicalResidualStrokeCount']
        entries = self.db.selectRows(select([table.c.ChineseCharacter,
                table.c.ZVariant, table.c.RadicalIndex, table.c.RadicalForm,
                table.c.RadicalZVariant, table.c.MainCharacterLayout,
                table.c.RadicalRelativePosition, table.c.ResidualStrokeCount])\
            .order_by(table.c.ResidualStrokeCount, table.c.RadicalZVariant,
                table.c.RadicalForm, table.c.MainCharacterLayout,
                table.c.RadicalRelativePosition))
        for entry in entries:
            char, zVariant, radicalIndex, radicalForm, radicalZVariant, \
                mainCharacterLayout, radicalReladtivePosition, \
                residualStrokeCount = entry

            if (char, zVariant) not in radicalDict:
                radicalDict[(char, zVariant)] = {}

            if radicalIndex  not in radicalDict[(char, zVariant)]:
                radicalDict[(char, zVariant)][radicalIndex] = []

            radicalDict[(char, zVariant)][radicalIndex].append(
                (radicalForm, radicalZVariant, mainCharacterLayout, \
                    radicalReladtivePosition, residualStrokeCount))

        return radicalDict

    def getCharacterKangxiResidualStrokeCount(self, char, zVariant=None):
        u"""
        Gets the stroke count of the residual character components when leaving
        aside the radical form.

        This method returns a subset of data with regards to
        L{getCharacterKangxiRadicalResidualStrokeCount()}. It may though offer
        more entries after all, as their might exists information only about
        the residual stroke count, but not about the concrete radical form.

        @type char: str
        @param char: Chinese character
        @type zVariant: int
        @param zVariant: I{Z-variant} of the first character. This parameter is
            optional and if omitted the default I{Z-variant} defined by
            L{getDefaultZVariant()} will be used.
        @rtype: int
        @return: residual stroke count
        @raise NoInformationError: if no stroke count information available
        @raise ValueError: if an invalid I{character locale} is specified
        @attention: The quality of the returned data depends on the sources used
            when compiling the database. Unihan itself only gives very general
            stroke order information without being bound to a specific glyph.
        """
        radicalIndex = self.getCharacterKangxiRadicalIndex(char)
        return self.getCharacterResidualStrokeCount(char, radicalIndex,
            zVariant)

    def getCharacterResidualStrokeCount(self, char, radicalIndex,
        zVariant=None):
        u"""
        Gets the stroke count of the residual character components when leaving
        aside the radical form.

        This is a more general version of
        L{getCharacterKangxiResidualStrokeCount()} which is not limited to the
        mapping of characters to a Kangxi radical as done by Unihan.

        @type char: str
        @param char: Chinese character
        @type radicalIndex: int
        @param radicalIndex: radical index
        @type zVariant: int
        @param zVariant: I{Z-variant} of the first character. This parameter is
            optional and if omitted the default I{Z-variant} defined by
            L{getDefaultZVariant()} will be used.
        @rtype: int
        @return: residual stroke count
        @raise NoInformationError: if no stroke count information available
        @raise ValueError: if an invalid I{character locale} is specified
        @attention: The quality of the returned data depends on the sources used
            when compiling the database. Unihan itself only gives very general
            stroke order information without being bound to a specific glyph.
        """
        if zVariant == None:
            zVariant = self.getDefaultZVariant(char)
        table = self.db.tables['CharacterResidualStrokeCount']
        entry = self.db.selectScalar(select([table.c.ResidualStrokeCount],
            and_(table.c.ChineseCharacter == char, table.c.ZVariant == zVariant,
                table.c.RadicalIndex == radicalIndex)))
        if entry != None:
            return entry
        else:
            raise exception.NoInformationError(
                "Character has no residual stroke count information")

    def getCharacterResidualStrokeCountDict(self):
        u"""
        Gets the table of stroke counts of the residual character components
        from the database for all characters in the chosen I{character domain}.

        A typical entry looks like C{(u'众', 0): {9: [4]}},
        and can be accessed as C{residualCountDict[(u'众', 0)][9]} with the
        Chinese character, its Z-variant and Kangxi radical index which then
        gives the I{residual stroke count}.

        @rtype: dict
        @return: dictionary of radical/residual stroke count entries.
        """
        residualCountDict = {}
        # get entries from database
        table = self.db.tables['CharacterResidualStrokeCount']
        # constrain to selected character domain
        if self.characterDomain == 'Unicode':
            fromObj = []
        else:
            fromObj = [table.join(self.characterDomainTable,
                table.c.ChineseCharacter \
                    == self.characterDomainTable.c.ChineseCharacter)]

        entries = self.db.selectRows(select([table.c.ChineseCharacter,
            table.c.ZVariant, table.c.RadicalIndex,
            table.c.ResidualStrokeCount], from_obj=fromObj))
        for entry in entries:
            char, zVariant, radicalIndex, residualStrokeCount = entry

            if (char, zVariant) not in residualCountDict:
                residualCountDict[(char, zVariant)] = {}

            residualCountDict[(char, zVariant)][radicalIndex] \
                = residualStrokeCount

        return residualCountDict

    def getCharactersForKangxiRadicalIndex(self, radicalIndex):
        """
        Gets all characters for the given Kangxi radical index.

        @type radicalIndex: int
        @param radicalIndex: Kangxi radical index
        @rtype: list of str
        @return: list of matching Chinese characters
        @todo Docu: Write about how Unihan maps characters to a Kangxi radical.
            Especially Chinese simplified characters.
        @todo Lang: 6954 characters have no Kangxi radical. Provide integration
            for these (SELECT COUNT(*) FROM Unihan WHERE kRSUnicode IS NOT NULL
            AND kRSKangxi IS NULL;).
        """
        table = self.db.tables['CharacterKangxiRadical']
        # constrain to selected character domain
        if self.characterDomain == 'Unicode':
            fromObj = []
        else:
            fromObj = [table.join(self.characterDomainTable,
                table.c.ChineseCharacter \
                    == self.characterDomainTable.c.ChineseCharacter)]

        return self.db.selectScalars(select([table.c.ChineseCharacter],
            table.c.RadicalIndex == radicalIndex, from_obj=fromObj))

    def getCharactersForRadicalIndex(self, radicalIndex):
        """
        Gets all characters for the given radical index.

        This is a more general version of
        L{getCharactersForKangxiRadicalIndex()} which is not limited to the
        mapping of characters to a Kangxi radical as done by Unihan and one
        character can show up under several different radical indices.

        @type radicalIndex: int
        @param radicalIndex: Kangxi radical index
        @rtype: list of str
        @return: list of matching Chinese characters
        """
        table = self.db.tables['CharacterResidualStrokeCount']
        # constrain to selected character domain
        if self.characterDomain == 'Unicode':
            fromObj = []
        else:
            fromObj = [table.join(self.characterDomainTable,
                table.c.ChineseCharacter \
                    == self.characterDomainTable.c.ChineseCharacter)]

        return self.db.selectScalars(select([table.c.ChineseCharacter],
            table.c.RadicalIndex == radicalIndex, from_obj=fromObj))

    def getResidualStrokeCountForKangxiRadicalIndex(self, radicalIndex):
        """
        Gets all characters and residual stroke count for the given Kangxi
        radical index.

        This brings together methods L{getCharactersForKangxiRadicalIndex()} and
        L{getCharacterResidualStrokeCountDict()} and reports all characters
        including the given Kangxi radical, additionally supplying the residual
        stroke count.

        @type radicalIndex: int
        @param radicalIndex: Kangxi radical index
        @rtype: list of tuple
        @return: list of matching Chinese characters with residual stroke count
        """
        kangxiTable = self.db.tables['CharacterKangxiRadical']
        residualTable = self.db.tables['CharacterResidualStrokeCount']
        fromObj = [residualTable.join(kangxiTable,
            and_(residualTable.c.ChineseCharacter \
                == kangxiTable.c.ChineseCharacter,
                residualTable.c.RadicalIndex == kangxiTable.c.RadicalIndex))]
        # constrain to selected character domain
        if self.characterDomain != 'Unicode':
            fromObj[0] = fromObj[0].join(self.characterDomainTable,
                residualTable.c.ChineseCharacter \
                    == self.characterDomainTable.c.ChineseCharacter)

        return self.db.selectRows(select([residualTable.c.ChineseCharacter,
            residualTable.c.ResidualStrokeCount],
            kangxiTable.c.RadicalIndex == radicalIndex, from_obj=fromObj))

    def getResidualStrokeCountForRadicalIndex(self, radicalIndex):
        """
        Gets all characters and residual stroke count for the given radical
        index.

        This brings together methods L{getCharactersForRadicalIndex()} and
        L{getCharacterResidualStrokeCountDict()} and reports all characters
        including the given radical without being limited to the mapping of
        characters to a Kangxi radical as done by Unihan, additionally supplying
        the residual stroke count.

        @type radicalIndex: int
        @param radicalIndex: Kangxi radical index
        @rtype: list of tuple
        @return: list of matching Chinese characters with residual stroke count
        """
        table = self.db.tables['CharacterResidualStrokeCount']
        # constrain to selected character domain
        if self.characterDomain == 'Unicode':
            fromObj = []
        else:
            fromObj = [table.join(self.characterDomainTable,
                table.c.ChineseCharacter \
                    == self.characterDomainTable.c.ChineseCharacter)]

        return self.db.selectRows(
            select([table.c.ChineseCharacter, table.c.ResidualStrokeCount],
                table.c.RadicalIndex == radicalIndex, from_obj=fromObj))

    #}
    #{ Radical form functions

    def getKangxiRadicalForm(self, radicalIdx):
        u"""
        Gets a I{Unicode radical form} for the given Kangxi radical index.

        This method will always return a single non null value, even if there
        are several radical forms for one index.

        @type radicalIdx: int
        @param radicalIdx: Kangxi radical index
        @rtype: str
        @return: I{Unicode radical form}
        @raise ValueError: if an invalid I{character locale} or radical index is
            specified
        @todo Lang: Check if radicals for which multiple radical forms exists
            include a simplified form or other variation (e.g. ⻆, ⻝, ⺐).
            There are radicals for which a Chinese simplified character
            equivalent exists and that is mapped to a different radical under
            Unicode.
        """
        if radicalIdx < 1 or radicalIdx > 214:
            raise ValueError("Radical index '" + unicode(radicalIdx) \
                + "' not in range between 1 and 214")

        table = self.db.tables['KangxiRadical']
        radicalForms = self.db.selectScalars(select([table.c.Form],
            and_(table.c.RadicalIndex == radicalIdx, table.c.Type == 'R',
                table.c.Locale.like(self._locale(self.locale))))\
            .order_by(table.c.SubIndex))
        return radicalForms[0]

    def getKangxiRadicalVariantForms(self, radicalIdx):
        """
        Gets a list of I{Unicode radical variant}s for the given Kangxi radical
        index.

        This method can return an empty list if there are no
        I{Unicode radical variant} forms. There might be non
        I{Unicode radical variant}s for this radial as character forms though.

        @type radicalIdx: int
        @param radicalIdx: Kangxi radical index
        @rtype: list of str
        @return: list of I{Unicode radical variant}s
        @raise ValueError: if an invalid I{character locale} is specified
        @todo Lang: Narrow locales, not all variant forms are valid under all
            locales.
        """
        table = self.db.tables['KangxiRadical']
        return self.db.selectScalars(select([table.c.Form],
            and_(table.c.RadicalIndex == radicalIdx, table.c.Type == 'V',
                table.c.Locale.like(self._locale(self.locale))))\
            .order_by(table.c.SubIndex))

    def getKangxiRadicalIndex(self, radicalForm):
        """
        Gets the Kangxi radical index for the given form.

        The given form might either be an I{Unicode radical form} or an
        I{equivalent character}.

        @type radicalForm: str
        @param radicalForm: radical form
        @rtype: int
        @return: Kangxi radical index
        @raise ValueError: if invalid I{character locale} or radical form is
            specified
        """
        # check in radical table
        locale = self._locale(self.locale)

        table = self.db.tables['KangxiRadical']
        result = self.db.selectScalar(select([table.c.RadicalIndex],
            and_(table.c.Form == radicalForm, table.c.Locale.like(locale))))
        if result:
            return result
        else:
            # check in radical equivalent character table, join tables
            kangxiTable = self.db.tables['KangxiRadical']
            equivalentTable = self.db.tables['RadicalEquivalentCharacter']
            result = self.db.selectScalars(select([kangxiTable.c.RadicalIndex],
                and_(equivalentTable.c.EquivalentForm == radicalForm,
                    equivalentTable.c.Locale.like(locale),
                    kangxiTable.c.Locale.like(locale)),
                from_obj=[kangxiTable.join(equivalentTable,
                    kangxiTable.c.Form == equivalentTable.c.Form)]))

            if result:
                return result[0]
            else:
                # check in isolated radical equivalent character table
                table = self.db.tables['KangxiRadicalIsolatedCharacter']
                result = self.db.selectScalar(select([table.c.RadicalIndex],
                    and_(table.c.EquivalentForm == radicalForm,
                        table.c.Locale.like(locale))))
                if result:
                    return result
        raise ValueError(radicalForm +  "is no valid Kangxi radical," \
            + " variant form or equivalent character")

    def getKangxiRadicalRepresentativeCharacters(self, radicalIdx):
        u"""
        Gets a list of characters that represent the radical for the given
        Kangxi radical index.

        This includes the radical form(s), character equivalents
        and variant forms and equivalents. Results are not limited to the chosen
        I{character domain}.

        E.g. character for I{to speak/to say/talk/word} (Pinyin I{yán}):
        ⾔ (0x2f94), 言 (0x8a00), ⻈ (0x2ec8), 讠 (0x8ba0), 訁 (0x8a01)

        @type radicalIdx: int
        @param radicalIdx: Kangxi radical index
        @rtype: list of str
        @return: list of Chinese characters representing the radical for the
            given index, including Unicode radical and variant forms and their
            equivalent real character forms
        @raise ValueError: if invalid I{character locale} specified
        """
        kangxiTable = self.db.tables['KangxiRadical']
        equivalentTable = self.db.tables['RadicalEquivalentCharacter']
        isolatedTable = self.db.tables['KangxiRadicalIsolatedCharacter']

        return self.db.selectScalars(union(
            select([kangxiTable.c.Form],
                and_(kangxiTable.c.RadicalIndex == radicalIdx,
                    kangxiTable.c.Locale.like(self._locale(self.locale)))),

            select([equivalentTable.c.EquivalentForm],
                and_(kangxiTable.c.RadicalIndex == radicalIdx,
                    equivalentTable.c.Locale.like(self._locale(self.locale)),
                    kangxiTable.c.Locale.like(self._locale(self.locale))),
                from_obj=[kangxiTable.join(equivalentTable,
                    kangxiTable.c.Form == equivalentTable.c.Form)]),

            select([isolatedTable.c.EquivalentForm],
                and_(isolatedTable.c.RadicalIndex == radicalIdx,
                    isolatedTable.c.Locale.like(self._locale(self.locale))))))

    def isKangxiRadicalFormOrEquivalent(self, form):
        """
        Checks if the given form is a Kangxi radical form or a radical
        equivalent. This includes I{Unicode radical form}s,
        I{Unicode radical variant}s, I{equivalent character} and
        I{isolated radical character}s.

        @type form: str
        @param form: Chinese character
        @rtype: bool
        @return: C{True} if given form is a radical or I{equivalent character},
            C{False} otherwise
        @raise ValueError: if an invalid I{character locale} is specified
        """
        try:
            self.getKangxiRadicalIndex(form)
            return True
        except ValueError:
            return False

    def isRadicalChar(self, char):
        """
        Checks if the given character is a I{Unicode radical form} or
        I{Unicode radical variant}.

        This method does a quick Unicode code index checking. So there is no
        guarantee this form has actually a radical entry in the database.

        @type char: str
        @param char: Chinese character
        @rtype: bool
        @return: C{True} if given form is a radical form, C{False} otherwise
        """
        # check if Unicode code point of character lies in between U+2e80 and
        # U+2fd5
        return char >= u'⺀' and char <= u'⿕'

    def getRadicalFormEquivalentCharacter(self, radicalForm):
        u"""
        Gets the I{equivalent character} of the given I{Unicode radical form} or
        I{Unicode radical variant}.

        The mapping mostly follows the X{Han Radical folding} specified in
        the Draft X{Unicode Technical Report #30} X{Character Foldings} under
        U{http://www.unicode.org/unicode/reports/tr30/#HanRadicalFolding}.
        All radical forms except U+2E80 (⺀) have an equivalent character. These
        equivalent characters are not necessarily visual identical and can be
        subject to major variation. Results are not limited to the chosen
        I{character domain}.

        This method may raise a UnsupportedError if there is no supported
        I{equivalent character} form.

        @type radicalForm: str
        @param radicalForm: I{Unicode radical form}
        @rtype: str
        @return: I{equivalent character} form
        @raise UnsupportedError: if there is no supported
            I{equivalent character} form
        @raise ValueError: if invalid I{character locale} or radical form is
            specified
        """
        if not self.isRadicalChar(radicalForm):
            raise ValueError(radicalForm + " is no valid radical form")

        table = self.db.tables['RadicalEquivalentCharacter']
        equivChar = self.db.selectScalar(select([table.c.EquivalentForm],
            and_(table.c.Form == radicalForm,
                table.c.Locale.like(self._locale(self.locale)))))
        if equivChar:
            return equivChar
        else:
            raise exception.UnsupportedError(
                "no equivalent character supported for '" + radicalForm + "'")

    def getCharacterEquivalentRadicalForms(self, equivalentForm):
        """
        Gets I{Unicode radical form}s or I{Unicode radical variant}s for the
        given I{equivalent character}.

        The mapping mostly follows the I{Han Radical folding} specified in
        the Draft I{Unicode Technical Report #30} I{Character Foldings} under
        U{http://www.unicode.org/unicode/reports/tr30/#HanRadicalFolding}.
        Several radical forms can be mapped to the same equivalent character
        and thus this method in general returns several values.

        @type equivalentForm: str
        @param equivalentForm: Equivalent character of I{Unicode radical form}
            or I{Unicode radical variant}
        @rtype: list of str
        @return: I{equivalent character} forms
        @raise ValueError: if invalid I{character locale} or equivalent
            character is specified
        """
        table = self.db.tables['RadicalEquivalentCharacter']
        result = self.db.selectScalars(select([table.c.Form],
            and_(table.c.EquivalentForm == equivalentForm,
                table.c.Locale.like(self._locale(self.locale)))))
        if result:
            return result
        else:
            raise ValueError(equivalentForm \
                + " is no valid equivalent character under the given locale")

    #}
    #{ Character component functions

    IDS_BINARY = [u'⿰', u'⿱', u'⿴', u'⿵', u'⿶', u'⿷', u'⿸', u'⿹', u'⿺',
        u'⿻']
    """
    A list of I{binary IDS operator}s used to describe character decompositions.
    """
    IDS_TRINARY = [u'⿲', u'⿳']
    """
    A list of I{trinary IDS operator}s used to describe character
    decompositions.
    """

    @classmethod
    def isBinaryIDSOperator(cls, char):
        """
        Checks if given character is a I{binary IDS operator}.

        @type char: str
        @param char: Chinese character
        @rtype: bool
        @return: C{True} if I{binary IDS operator}, C{False} otherwise
        """
        return char in set(cls.IDS_BINARY)

    @classmethod
    def isTrinaryIDSOperator(cls, char):
        """
        Checks if given character is a I{trinary IDS operator}.

        @type char: str
        @param char: Chinese character
        @rtype: bool
        @return: C{True} if I{trinary IDS operator}, C{False} otherwise
        """
        return char in set(cls.IDS_TRINARY)

    @classmethod
    def isIDSOperator(cls, char):
        """
        Checks if given character is an I{IDS operator}.

        @type char: str
        @param char: Chinese character
        @rtype: bool
        @return: C{True} if I{IDS operator}, C{False} otherwise
        """
        return cls.isBinaryIDSOperator(char) or cls.isTrinaryIDSOperator(char)

    def getCharactersForComponents(self, componentList,
        includeEquivalentRadicalForms=True, resultIncludeRadicalForms=False):
        u"""
        Gets all characters that contain the given components.

        If option C{includeEquivalentRadicalForms} is set, all equivalent forms
        will be search for when a Kangxi radical is given.

        @type componentList: list of str
        @param componentList: list of character components
        @type includeEquivalentRadicalForms: bool
        @param includeEquivalentRadicalForms: if C{True} then characters in the
            given component list are interpreted as representatives for their
            radical and all radical forms are included in the search. E.g. 肉
            will include ⺼ as a possible component.
        @type resultIncludeRadicalForms: bool
        @param resultIncludeRadicalForms: if C{True} the result will include
            I{Unicode radical forms} and I{Unicode radical variants}
        @rtype: list of tuple
        @return: list of pairs of matching characters and their Z-variants
        @raise ValueError: if an invalid I{character locale} is specified
        @todo Impl: Table of same character glyphs, including special radical
            forms (e.g. 言 and 訁).
        @todo Data: Adopt locale dependant Z-variants for parent characters
            (e.g. 鬼 in 隗 愧 嵬).
        @todo Data: Use radical forms and radical variant forms instead of
            equivalent characters in decomposition data. Mapping looses
            information.
        @todo Lang: By default we get the equivalent character for a radical
            form. In some cases these equivalent characters will be only
            abstractly related to the given radical form (e.g. being the main
            radical form), so that the result set will be too big and doesn't
            reflect the original query. Set up a table including only strict
            visual relations between radical forms and equivalent characters.
            Alternatively restrict decomposition data to only include radical
            forms if appropriate, so there would be no need for conversion.
        """
        equivCharTable = []
        for component in componentList:
            try:
                # check if component is a radical and get index
                radicalIdx = self.getKangxiRadicalIndex(component)

                componentEquivalents = [component]
                if includeEquivalentRadicalForms:
                    # if includeRadicalVariants is set get all forms
                    componentEquivalents = \
                        self.getKangxiRadicalRepresentativeCharacters(
                            radicalIdx)
                else:
                    if self.isRadicalChar(component):
                        try:
                            componentEquivalents.append(
                                self.getRadicalFormEquivalentCharacter(
                                    component))
                        except exception.UnsupportedError:
                            # pass if no equivalent char existent
                            pass
                    else:
                        componentEquivalents.extend(
                            self.getCharacterEquivalentRadicalForms(component))
                equivCharTable.append(componentEquivalents)
            except ValueError:
                equivCharTable.append([component])

        return self.getCharactersForEquivalentComponents(equivCharTable,
            resultIncludeRadicalForms=resultIncludeRadicalForms)

    def getCharactersForEquivalentComponents(self, componentConstruct,
        resultIncludeRadicalForms=False, includeAllZVariants=False):
        u"""
        Gets all characters that contain at least one component per list entry,
        sorted by stroke count if available.

        This is the general form of L{getCharactersForComponents()} and allows a
        set of characters per list entry of which at least one character must be
        a component in the given list.

        @type componentConstruct: list of list of str
        @param componentConstruct: list of character components given as single
            characters or, for alternative characters, given as a list
        @type resultIncludeRadicalForms: bool
        @param resultIncludeRadicalForms: if C{True} the result will include
            I{Unicode radical forms} and I{Unicode radical variants}
        @type includeAllZVariants: bool
        @param includeAllZVariants: if C{True} all matches will be returned, if
            C{False} only those with z-Variant matching the locale's default one
            will be returned
        @rtype: list of tuple
        @return: list of pairs of matching characters and their Z-variants
        @raise ValueError: if an invalid I{character locale} is specified
        """
        if not componentConstruct:
            return []

        # create where clauses
        lookupTable = self.db.tables['ComponentLookup']
        localeTable = self.db.tables['LocaleCharacterVariant']
        strokeCountTable = self.db.tables['StrokeCount']

        joinTables = []         # join over all tables by char and z-Variant
        filters = []            # filter for locale and component

        # generate filter for each component
        for i, characterList in enumerate(componentConstruct):
            lookupTableAlias = lookupTable.alias('s%d' % i)
            joinTables.append(lookupTableAlias)
            # find chars for components, also include 米 for [u'米', u'木'].
            filters.append(or_(lookupTableAlias.c.Component.in_(characterList),
                lookupTableAlias.c.ChineseCharacter.in_(characterList)))

        # join with LocaleCharacterVariant and allow only forms matching the
        #   given locale, unless includeAllZVariants is True
        if not includeAllZVariants:
            joinTables.append(localeTable)
            filters.append(or_(localeTable.c.Locale == None,
                localeTable.c.Locale.like(self._locale(self.locale))))

        # include stroke count to sort
        if self.hasStrokeCount:
            joinTables.append(strokeCountTable)

        # chain tables together in a JOIN
        fromObject = joinTables[0]
        for table in joinTables[1:]:
            fromObject = fromObject.outerjoin(table,
                onclause=and_(
                    table.c.ChineseCharacter \
                        == joinTables[0].c.ChineseCharacter,
                    table.c.ZVariant == joinTables[0].c.ZVariant))
        # constrain to selected character domain
        if self.characterDomain != 'Unicode':
            fromObject = fromObject.join(self.characterDomainTable,
                joinTables[-1].c.ChineseCharacter \
                    == self.characterDomainTable.c.ChineseCharacter)

        sel = select([joinTables[0].c.ChineseCharacter,
            joinTables[0].c.ZVariant], and_(*filters), from_obj=[fromObject],
            distinct=True)
        if self.hasStrokeCount:
            sel = sel.order_by(strokeCountTable.c.StrokeCount)

        result = self.db.selectRows(sel)

        if not resultIncludeRadicalForms:
            # exclude radical characters found in decomposition
            result = [(char, zVariant) for char, zVariant in result \
                if not self.isRadicalChar(char)]

        return result

    def getDecompositionEntries(self, char, zVariant=None):
        """
        Gets the decomposition of the given character into components from the
        database. The resulting decomposition is only the first layer in a tree
        of possible paths along the decomposition as the components can be
        further subdivided.

        There can be several decompositions for one character so a list of
        decomposition is returned.

        Each entry in the result list consists of a list of characters (with its
        Z-variant) and IDS operators.

        @type char: str
        @param char: Chinese character that is to be decomposed into components
        @type zVariant: int
        @param zVariant: I{Z-variant} of the first character. This parameter is
            optional and if omitted the default I{Z-variant} defined by
            L{getDefaultZVariant()} will be used.
        @rtype: list
        @return: list of first layer decompositions
        @raise ValueError: if an invalid I{character locale} is specified
        """
        if zVariant == None:
            try:
                zVariant = self.getDefaultZVariant(char)
            except exception.NoInformationError:
                # no decomposition available
                return []

        # get entries from database
        table = self.db.tables['CharacterDecomposition']
        result = self.db.selectScalars(select([table.c.Decomposition],
            and_(table.c.ChineseCharacter == char,
                table.c.ZVariant == zVariant)).order_by(table.c.SubIndex))

        # extract character Z-variant information (example entry: '⿱卜[1]尸')
        return [self._getDecompositionFromString(decomposition) \
            for decomposition in result]

    def getDecompositionEntriesDict(self):
        """
        Gets the decomposition table from the database for all characters in the
        chosen I{character domain}.

        @rtype: dict
        @return: dictionary with key pair character, Z-variant and the first
            layer decomposition as value
        """
        decompDict = {}
        # get entries from database
        table = self.db.tables['CharacterDecomposition']
        # constrain to selected character domain
        if self.characterDomain == 'Unicode':
            fromObj = []
        else:
            fromObj = [table.join(self.characterDomainTable,
                table.c.ChineseCharacter \
                    == self.characterDomainTable.c.ChineseCharacter)]

        entries = self.db.selectRows(select([table.c.ChineseCharacter,
            table.c.ZVariant, table.c.Decomposition], from_obj=fromObj)\
                .order_by(table.c.SubIndex))
        for char, zVariant, decomposition in entries:
            if (char, zVariant) not in decompDict:
                decompDict[(char, zVariant)] = []

            decompDict[(char, zVariant)].append(
                self._getDecompositionFromString(decomposition))

        return decompDict

    def _getDecompositionFromString(self, decomposition):
        """
        Gets a tuple representation with character/Z-variant of the given
        character's decomposition into components.

        Example: Entry C{⿱尚[1]儿} will be returned as
        C{[u'⿱', (u'尚', 1), (u'儿', 0)]}.

        @type decomposition: str
        @param decomposition: character decomposition with IDS operator,
            compontens and optional Z-variant index
        @rtype: list
        @return: decomposition with character/Z-variant tuples
        """
        componentsList = []
        index = 0
        while index < len(decomposition):
            char = decomposition[index]
            if self.isIDSOperator(char):
                componentsList.append(char)
            else:
                # is Chinese character
                if index+1 < len(decomposition)\
                    and decomposition[index+1] == '[':

                    endIndex = decomposition.index(']', index+1)
                    # extract Z-variant information
                    charZVariant = int(decomposition[index+2:endIndex])
                    index = endIndex
                else:
                    # take default Z-variant if none specified
                    charZVariant = 0
                componentsList.append((char, charZVariant))
            index = index + 1
        return componentsList

    def getDecompositionTreeList(self, char, zVariant=None):
        """
        Gets the decomposition of the given character into components as a list
        of decomposition trees.

        There can be several decompositions for one character so one tree per
        decomposition is returned.

        Each entry in the result list consists of a list of characters (with its
        Z-variant and list of further decomposition) and IDS operators. If a
        character can be further subdivided, its containing list is non empty
        and includes yet another list of trees for the decomposition of the
        component.

        @type char: str
        @param char: Chinese character that is to be decomposed into components
        @type zVariant: int
        @param zVariant: I{Z-variant} of the first character. This parameter is
            optional and if omitted the default I{Z-variant} defined by
            L{getDefaultZVariant()} will be used.
        @rtype: list
        @return: list of decomposition trees
        @raise ValueError: if an invalid I{character locale} is specified
        """
        if zVariant == None:
            try:
                zVariant = self.getDefaultZVariant(char)
            except exception.NoInformationError:
                # no decomposition available
                return []

        decompositionTreeList = []
        # get tree for each decomposition
        for componentsList in self.getDecompositionEntries(char,
            zVariant=zVariant):
            decompositionTree = []
            for component in componentsList:
                if type(component) != type(()):
                    # IDS operator
                    decompositionTree.append(component)
                else:
                    # Chinese character with zVariant info
                    character, characterZVariant = component
                    # get partition of component recursively
                    componentTree = self.getDecompositionTreeList(character,
                        zVariant=characterZVariant)
                    decompositionTree.append((character, characterZVariant,
                        componentTree))
            decompositionTreeList.append(decompositionTree)
        return decompositionTreeList

    def isComponentInCharacter(self, component, char, zVariant=None,
        componentZVariant=None):
        """
        Checks if the given character contains the second character as a
        component.

        @type component: str
        @param component: character questioned to be a component
        @type char: str
        @param char: Chinese character
        @type zVariant: int
        @param zVariant: I{Z-variant} of the first character. This parameter is
            optional and if omitted the default I{Z-variant} defined by
            L{getDefaultZVariant()} will be used.
        @type componentZVariant: int
        @param componentZVariant: Z-variant of the component; if left out every
            Z-variant matches for that character.
        @rtype: bool
        @return: C{True} if C{component} is a component of the given character,
            C{False} otherwise
        @raise ValueError: if an invalid I{character locale} is specified
        @todo Impl: Implement means to check if the component is really not
            found, or if our data is just insufficient.
        """
        if zVariant == None:
            try:
                zVariant = self.getDefaultZVariant(char)
            except exception.NoInformationError:
                # TODO no way to check if our data is insufficent
                return False

        # if table exists use it to speed up look up
        if self.hasComponentLookup:
            table = self.db.tables['ComponentLookup']
            zVariants = self.db.selectScalars(
                select([table.c.ComponentZVariant],
                    and_(table.c.ChineseCharacter == char,
                        table.c.ZVariant == zVariant,
                        table.c.Component == component)))
            return len(zVariants) > 0 and (componentZVariant == None \
                or componentZVariant in zVariants)
        else:
            # use slow way with going through the decomposition tree
            # get decomposition for the first character from table
            for componentsList in self.getDecompositionEntries(char,
                zVariant=zVariant):
                # got through decomposition and check for components
                for charComponent in componentsList:
                    if type(charComponent) == type(()):
                        character, characterZVariant = charComponent
                        if character != u'？':
                            # check if character and Z-variant match
                            if character == component \
                                and (componentZVariant == None or
                                    characterZVariant == componentZVariant):
                                return True
                            # else recursively step into decomposition of
                            #   current component
                            if self.isComponentInCharacter(character, component,
                                zVariant=characterZVariant,
                                componentZVariant=componentZVariant):
                                return True
            return False
