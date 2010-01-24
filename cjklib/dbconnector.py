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
Provides simple read access to SQL databases.
"""

import os
import logging
import glob

from sqlalchemy import MetaData, Table, engine_from_config
from sqlalchemy.sql import text
from sqlalchemy.engine.url import make_url

from cjklib.util import getConfigSettings, getSearchPaths, LazyDict, OrderedDict

class DatabaseConnector:
    """
    A DatabaseConnector connects to one or more SQL databases. It provides four
    simple methods for retrieving scalars or rows of data:
        1. C{selectScalar()}: returns one single value
        2. C{selectRow()}: returns only one entry with several columns
        3. C{selectScalars()}: returns entries for a single column
        4. C{selectRows()}: returns multiple entries for multiple columns

    This class takes care to load the correct database(s). It provides for
    attaching further databases and gives any program that depends on cjklib the
    possibility to easily add own data in databases outside cjklib extending the
    library's information.

    Example:

        >>> from cjklib.dbconnector import DatabaseConnector
        >>> from sqlalchemy import select
        >>> db = DatabaseConnector.getDBConnector()
        >>> db.selectScalar(select([db.tables['Strokes'].c.Name],
        ...     db.tables['Strokes'].c.StrokeAbbrev == 'T'))
        u'\u63d0'

    DatabaseConnector is tested on SQLite and MySQL but should support most
    other database systems through I{SQLAlchemy}.

    Multiple database support
    =========================
    A DatabaseConnector instance is attached to a main database. Further
    databases can be attached at any time, providing further tables. Tables from
    the main database will shadow any other table with a similar name. A table
    not found in the main database will be chosen from a database in the order
    of their attachment.

    The L{tables} dictionary allows simple lookup of table objects by short
    name, without the need of knowing the full qualified name including the
    database specifier. Existence of tables can be checked using L{hasTable()};
    L{tables} will only include table information after the first access. All
    table names can be retrieved with L{getTableNames()}.

    Table lookup is designed with a stable data set in mind. Moving tables
    between databases is not especially supported and while operations through
    the L{build} module will update any information in the L{tables} dictionary,
    manual creating and dropping of a table or changing its structure will lead
    to the dictionary having obsolete information. This can be circumvented by
    deleting keys forcing an update.

    Example:

        >>> from cjklib.dbconnector import DatabaseConnector
        >>> db = DatabaseConnector({'url': 'sqlite:////tmp/mydata.db',
        ...     'attach': ['cjklib']})
        >>> db.tables['StrokeOrder'].fullname
        'cjklib_0.StrokeOrder'

    Discovery of attachable databases
    =================================
    DatabaseConnector has the ability to discover databases attaching them to
    the main database. Specifying databases can be done in three ways:
        1. A full URL can be given denoting a single database, e.g.
           X{'sqlite:////tmp/mydata.db'}.
        2. Giving a directory will add any .db file as SQLite database, e.g.
           X{'/usr/local/share/cjklib'}.
        3. Giving a project name will prompt DatabaseConnector to check for
           a project config file and add databases specified there and/or scan
           that project's default directories, e.g. X{'cjklib'}.
    """
    _dbconnectInst = None
    """
    Instance of a L{DatabaseConnector} used for all connections to SQL server.
    """
    _dbconnectInstSettings = None
    """
    Database url used to create the connector instance.
    """

    @classmethod
    def getDBConnector(cls, configuration=None, projectName='cjklib'):
        """
        Returns a shared L{DatabaseConnector} instance.

        To connect to a user specific database give
        C{{'sqlalchemy.url': 'driver://user:pass@host/database'}} as
        configuration.

        See the documentation of sqlalchemy.create_engine() for more options.

        @param configuration: database connection options (includes settings for
            SQLAlchemy prefixed by C{'sqlalchemy.'})
        @type projectName: str
        @param projectName: name of project which will be used as name of the
            config file
        """
        # allow single string and interpret as url
        if isinstance(configuration, basestring):
            configuration = {'sqlalchemy.url': configuration}
        elif not configuration:
            # try to read from config
            configuration = getConfigSettings('Connection', projectName)

            if ('url' not in configuration
                and 'sqlalchemy.url' not in configuration):
                configuration['sqlalchemy.url'] = cls._getDefaultDB(projectName)

        # if settings changed, remove old instance
        if not cls._dbconnectInstSettings \
            or cls._dbconnectInstSettings != configuration:
            cls._dbconnectInst = None

        if not cls._dbconnectInst:
            databaseSettings = configuration.copy()

            cls._dbconnectInst = DatabaseConnector(databaseSettings)
            cls._dbconnectInstSettings = databaseSettings

        return cls._dbconnectInst

    @classmethod
    def _getDefaultDB(cls, projectName='cjklib'):
        """
        Gets the default database URL for the given project.

        @type projectName: str
        @param projectName: name of project which will be used as the name of
            the database
        """
        try:
            from pkg_resources import Requirement, resource_filename
            dbFile = resource_filename(Requirement.parse(projectName),
                '%(proj)s/%(proj)s.db' % {'proj': projectName})
        except ImportError:
            libdir = os.path.dirname(os.path.abspath(__file__))
            dbFile = os.path.join(libdir, '%(proj)s.db' % {'proj': projectName})

        return 'sqlite:///%s' % dbFile

    def __init__(self, configuration):
        """
        Constructs the DatabaseConnector object and connects to the database
        specified by the options given in databaseSettings.

        To connect to a user specific database give
        C{{'sqlalchemy.url': 'driver://user:pass@host/database'}} as
        configuration.

        See the documentation of sqlalchemy.create_engine() for more options.

        @type configuration: dict
        @param configuration: database connection options for SQLAlchemy
        @todo Fix: Do we need to register views?
        """
        configuration = configuration or {}
        if isinstance(configuration, basestring):
            # backwards compatibility to option databaseUrl
            configuration = {'sqlalchemy.url': configuration}

        # allow 'url' as parameter, but move to 'sqlalchemy.url'
        if 'url' in configuration:
            if ('sqlalchemy.url' in configuration
                and configuration['sqlalchemy.url'] != configuration['url']):
                raise ValueError("Two different URLs specified"
                    " for 'url' and 'sqlalchemy.url'."
                    "Check your configuration.")
            else:
                configuration['sqlalchemy.url'] = configuration.pop('url')

        self.databaseUrl = configuration['sqlalchemy.url']
        """Database url"""

        self.engine = engine_from_config(configuration, prefix='sqlalchemy.')
        """SQLAlchemy engine object"""
        self.connection = self.engine.connect()
        """SQLAlchemy database connection object"""
        self.metadata = MetaData(bind=self.connection)
        """SQLAlchemy metadata object"""

        # multi-database table access
        self.tables = LazyDict(self._tableGetter())
        """Dictionary of SQLAlchemy table objects"""

        if self.engine.name == 'sqlite':
            # Main database can be prefixed with 'main.'
            self._mainSchema = 'main'
        else:
            # MySQL uses database name for prefix
            self._mainSchema = self.engine.url.database

        # attach other databases
        self.attached = OrderedDict()
        """Mapping of attached database URLs to internal schema names"""
        attach = configuration.pop('attach', [])
        if isinstance(attach, basestring): attach = attach.split('\n')

        for url in self._findAttachableDatabases(attach):
            self.attachDatabase(url)

        # register views
        self._registerViews()

    def _findAttachableDatabases(self, attachList):
        """
        Returns URLs for databases that can be attached to a given database.
        """
        attachable = []
        for name in attachList:
            if '://' in name:
                # database url
                attachable.append(name)
            elif os.path.isabs(name):
                # path
                if not os.path.exists(name):
                    continue
                attachable.extend([('sqlite:///%s' % f)
                    for f in glob.glob(os.path.join(name, "*.db"))])

            elif '/' not in name and '\\' not in name:
                # project name
                configuration = getConfigSettings('Connection', name)

                # first add main database
                if 'url' in configuration:
                    url = configuration['url']
                elif 'sqlalchemy.url' in configuration:
                    url = configuration['sqlalchemy.url']
                else:
                    url = self._getDefaultDB(name)
                attachable.append(url)

                # add attachables from the given project
                if 'attach' in configuration:
                    subSearchPath = configuration['attach'].split('\n')
                else:
                    subSearchPath = getSearchPaths(name)

                attachable.extend(self._findAttachableDatabases(subSearchPath))
            else:
                raise ValueError("Invalid database reference '%s'" % name)

        return attachable

    def _registerViews(self):
        """
        Registers all views and makes them accessible through the same methods
        as tables in SQLAlchemy.

        @rtype: list of str
        @return: List of registered views
        @attention: Currently only works for MySQL and SQLite.
        @todo Impl: registering for all attached databases
        """
        if self.engine.name == 'mysql':
            dbName = self.engine.url.database
            viewList = self.execute(
                text("SELECT table_name FROM Information_schema.views"
                    " WHERE table_schema = :dbName"),
                dbName=dbName).fetchall()
        elif self.engine.name == 'sqlite':
            viewList = self.execute(
                text("SELECT name FROM sqlite_master WHERE type IN ('view')"))\
                .fetchall()
        else:
            logging.warning("Don't know how to get all views from database."
                " Unable to register."
                " Views will not show up in list of available tables.")
            return

        for viewName, in viewList:
            # add views that are currently not (well) supported by SQLalchemy
            #   http://www.sqlalchemy.org/trac/ticket/812
            Table(viewName, self.metadata, autoload=True)

        return [viewName for viewName, in viewList]

    def attachDatabase(self, databaseUrl):
        """
        Attaches a database to the main database.

        @type databaseUrl: str
        @param databaseUrl: database URL
        @rtype: str
        @return: the database's schema used to access its tables, C{None} if
            that database has been attached before
        """
        if databaseUrl == self.databaseUrl or databaseUrl in self.attached:
            return

        url = make_url(databaseUrl)
        if url.drivername != self.engine.name:
            raise ValueError("Incompatible engines")

        if self.engine.name == 'sqlite':
            databaseFile = url.database

            _, dbName = os.path.split(databaseFile)
            if dbName.endswith('.db'): dbName = dbName[:-3]
            schema = '%s_%d' % (dbName, len(self.attached))

            self.execute(text("""ATTACH DATABASE :database AS :schema"""),
                database=databaseFile, schema=schema)
        else:
            schema = url.database

        self.attached[databaseUrl] = schema

        return schema

    def getTableNames(self):
        """"
        Gets the unique list of names of all tables (and views) from the
        databases.

        @rtype: iterable
        @return: all tables and views
        """
        tables = set(self._registerViews())
        tables.update(self.engine.table_names(schema=self._mainSchema))
        for schema in self.attached.values():
            tables.update(self.engine.table_names(schema=schema))

        return tables

    def _tableGetter(self):
        """
        Returns a function that retrieves a SQLAlchemy Table object for a given
        table name.
        """
        def getTable(tableName):
            schema = self._findTable(tableName)
            if schema is not None:
                return Table(tableName, self.metadata, autoload=True,
                    autoload_with=self.engine, schema=schema)

            raise KeyError("Table '%s' not found in any database")

        return getTable

    def _findTable(self, tableName):
        """
        Gets the schema (database name) of the database that offers the given
        table.

        The databases will be accessed in the order as attached.

        @type tableName: str
        @param tableName: name of table to be located
        @rtype: str
        @return: schema name of database including table
        """
        if self.engine.has_table(tableName, schema=self._mainSchema):
            return self._mainSchema
        else:
            for schema in self.attached.values():
                if self.engine.has_table(tableName, schema=schema):
                    return schema
        return None

    def hasTable(self, tableName):
        """
        Returns C{True} if the given table exists in one of the databases.

        @type tableName: str
        @param tableName: name of table to be located
        @rtype: bool
        @return: C{True} if table is found, C{False} otherwise
        """
        schema = self._findTable(tableName)
        return schema is not None

    def mainHasTable(self, tableName):
        """
        Returns C{True} if the given table exists in the main database.

        @type tableName: str
        @param tableName: name of table to be located
        @rtype: bool
        @return: C{True} if table is found, C{False} otherwise
        """
        return self.engine.has_table(tableName, schema=self._mainSchema)

    def execute(self, *options, **keywords):
        """
        Executes a request on the given database.
        """
        return self.connection.execute(*options, **keywords)

    def _decode(self, data):
        """
        Decodes a data row.

        MySQL will currently return utf8_bin collated values as string object
        encoded in utf8. We need to fix that here.
        @param data: a tuple or scalar value
        """
        if type(data) == type(()):
            newData = []
            for cell in data:
                if type(cell) == type(''):
                    cell = cell.decode('utf8')
                newData.append(cell)
            return tuple(newData)
        else:
            if type(data) == type(''):
                return data.decode('utf8')
            else:
                return data

    # select commands

    def selectScalar(self, request):
        """
        Executes a select query and returns a single variable.

        @param request: SQL request
        @return: a scalar
        """
        result = self.execute(request)
        assert result.rowcount <= 1
        firstRow = result.fetchone()
        assert not firstRow or len(firstRow) == 1
        if firstRow:
            return self._decode(firstRow[0])

    def selectScalars(self, request):
        """
        Executes a select query and returns a list of scalars.

        @param request: SQL request
        @return: a list of scalars
        """
        result = self.execute(request)
        return [self._decode(row[0]) for row in result.fetchall()]

    def selectRow(self, request):
        """
        Executes a select query and returns a single table row.

        @param request: SQL request
        @return: a list of scalars
        """
        result = self.execute(request)
        assert result.rowcount <= 1
        firstRow = result.fetchone()
        if firstRow:
            return self._decode(tuple(firstRow))

    def selectRows(self, request):
        """
        Executes a select query and returns a list of table rows.

        @param request: SQL request
        @return: a list of scalars
        """
        result = self.execute(request)
        return [self._decode(tuple(row)) for row in result.fetchall()]
