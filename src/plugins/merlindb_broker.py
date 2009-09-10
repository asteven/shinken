#!/usr/bin/python
#Copyright (C) 2009 Gabes Jean, naparuba@gmail.com
#
#This file is part of Shinken.
#
#Shinken is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#Shinken is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU Affero General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with Shinken.  If not, see <http://www.gnu.org/licenses/>.

import copy


#This text is print at the import
print "I am Merlin Broker"


#called by the plugin manager to get a broker
def get_broker():
    broker = Merlindb_broker()
    return broker


#Class for the Merlindb Broker
#Get broks and puts them in merlin database
class Merlindb_broker:
    def __init__(self):
        pass


    #The classic has : do we have a prop or not?
    def has(self, prop):
        return hasattr(self, prop)


    def init(self):
        print "I connect to database, thanks"
        self.connect_database()
    

    #Get a brok, parse it, and put in in database
    #We call functions like manage_ TYPEOFBROK _brok that return us queries
    def manage_brok(self, b):
        type = b.type
        manager = 'manage_'+type+'_brok'
        print "(Merlin) I search manager:", manager
        #print "My dict:", self.__dict__, dir(self)
        if self.has(manager):
            f = getattr(self, manager)
            queries = f(b)
            for q in queries :
                self.execute_query(q)
            return
        print "(merlindb)I don't manage this brok type", b


    #Create the database connexion
    #TODO : finish error catch
    def connect_database(self):
        import MySQLdb
        self.db = MySQLdb.connect (host = "localhost", user = "root", passwd = "root",db = "merlin")
        self.db_cursor = self.db.cursor ()


    #Just run the query
    #TODO: finish catch
    def execute_query(self, query):
        #print "I run query", query, "\n"
        self.db_cursor.execute (query)
        self.db.commit ()


    #Create a INSERT query in table with all data of data (a dict)
    def create_insert_query(self, table, data):
        query = "INSERT INTO %s " % table
        props_str = ' ('
        values_str = ' ('
        i = 0 #for the ',' problem... look like C here...
        for prop in data:
            i += 1
            val = data[prop]
			#Boolean must be catch, because we want 0 or 1, not True or False
            if isinstance(val, bool):
                if val:
                    val = 1
                else:
                    val = 0
            if i == 1:
                props_str = props_str + "%s " % prop
                values_str = values_str + "'%s' " % val
            else:
                props_str = props_str + ", %s " % prop
                values_str = values_str + ", '%s' " % val

        #Ok we've got data, let's finish the query
        props_str = props_str + ' )'
        values_str = values_str + ' )'
        query = query + props_str + 'VALUES' + values_str
        return query

    
    #Create a update query of table with data, and use where data for the WHERE clause
    def create_update_query(self, table, data, where_data):
        #We want a query like :
        #INSERT INTO example (name, age) VALUES('Timmy Mellowman', '23' )
        query = "UPDATE %s set " % table
		
        #First data manage
        query_folow = ''
        i = 0 #for the , problem...
        for prop in data:
            i += 1
            val = data[prop]
			#Boolean must be catch, because we want 0 or 1, not True or False
            if isinstance(val, bool):
                if val:
                    val = 1
                else:
                    val = 0
            if i == 1:
                query_folow += "%s='%s' " % (prop, val)
            else:
                query_folow += ", %s='%s' " % (prop, val)
                
        #Ok for data, now WHERE, same things
        where_clause = " WHERE "
        i = 0 # For the 'and' problem
        for prop in where_data:
            i += 1
            val = where_data[prop]
            #Boolean must be catch, because we want 0 or 1, not True or False
            if isinstance(val, bool):
                if val:
                    val = 1
                else:
                    val = 0
            if i == 1:
                where_clause += "%s='%s' " % (prop, val)
            else:
                where_clause += "and %s='%s' " % (prop, val)

        query = query + query_folow + where_clause#" WHERE host_name = '%s' AND service_description = '%s'" % (data['host_name'] , data['service_description'])				
        return query
    
    
    #Ok, we are at launch and a scheduler want him only, OK...
    #So ca create several queries with all tables we need to delete with our instance_id
    #This brob must be send at the begining of a scheduler session, if not, BAD THINGS MAY HAPPENED :)
    def manage_clean_all_my_instance_id_brok(self, b):
        instance_id = b.data['instance_id']
        tables = ['command', 'comment', 'contact', 'contactgroup', 'downtime', 'host', 
                  'hostdependency', 'hostescalation', 'hostgroup', 'notification', 'program_status', 
                  'scheduled_downtime', 'service',  'serviceescalation',
                  'servicegroup', 'timeperiod']
        res = []
        for table in tables:
            q = "DELETE FROM %s WHERE instance_id = '%s' " % (table, instance_id)
            res.append(q)
        return res


    #Get a brok, parse it, and return the queries for database
    def manage_program_status_brok(self, b):
        data = b.data

        #We want a query like :
        #INSERT INTO example (name, age) VALUES('Timmy Mellowman', '23' )
        query = self.create_insert_query('program_status', data)

        return [query]


    #Get a brok, parse it, and return the query for database
    def manage_initial_service_status_brok(self, b):
        data = b.data
        #It's a initial entry, so we need to clean old entries
        #delete_query = "DELETE FROM service WHERE host_name = '%s' AND service_description = '%s'" % (data['host_name'], data['service_description'])

        query = self.create_insert_query('service', data)		

        return [query]


    #Get a brok, parse it, and return the query for database
    def manage_service_check_result_brok(self, b):
        data = b.data
        
        where_clause = {'host_name' : data['host_name'] , 'service_description' : data['service_description']}
        query = self.create_update_query('service', data, where_clause)

        return [query]


    #Get a brok, parse it, and return the query for database
    def manage_update_service_status_brok(self, b):
        data = b.data
		
        where_clause = {'host_name' : data['host_name'] , 'service_description' : data['service_description']}
        query = self.create_update_query('service', data, where_clause)
        
        return [query]



    #Get a brok, parse it, and return the query for database
    def manage_initial_host_status_brok(self, b):
        data = b.data
        #It's a initial entry, so we need to clean old entries
        #delete_query = "DELETE FROM host WHERE host_name = '%s'" % data['host_name']

        query = self.create_insert_query('host', data)

        return [query]


    #Get a brok, parse it, and return the query for database
    def manage_initial_hostgroup_status_brok(self, b):
        data = b.data
        #Here we've got a special case : in data, there is members
        #and we do not want it in the INSERT query, so we crate a tmp_data without it
        tmp_data = copy.copy(data)
        del tmp_data['members']
        query = self.create_insert_query('hostgroup', tmp_data)

        res = [query]
		
        #Ok, the hostgroup table is uptodate, now we add relations between hosts and hostgroups
        for (h_id, h_name) in b.data['members']:
            #First clean
            q_del = "DELETE FROM host_hostgroup WHERE host = '%s' and hostgroup='%s'" % (h_id, b.data['id'])
            res.append(q_del)
            #Then add
            q = "INSERT INTO host_hostgroup (host, hostgroup) VALUES ('%s', '%s')" % (h_id, b.data['id'])
            res.append(q)
        return res


    #Get a brok, parse it, and return the query for database
    def manage_initial_servicegroup_status_brok(self, b):
        data = b.data
        #It's a initial entry, so we need to clean old entries
        delete_query = "DELETE FROM servicegroup WHERE servicegroup_name = '%s'" % data['servicegroup_name']

        #Here we've got a special case : in data, there is members
        #and we do not want it in the INSERT query, so we crate a tmp_data without it
        tmp_data = copy.copy(data)
        del tmp_data['members']
        query = self.create_insert_query('servicegroup', tmp_data)

        res = [delete_query, query]

        for (s_id, s_name) in b.data['members']:
            #first clean
            q_del = "DELETE FROM service_servicegroup WHERE service='%s' and servicegroup='%s'" % (s_id, b.data['id'])
            res.append(q_del)
            #Then add
            q = "INSERT INTO service_servicegroup (service, servicegroup) VALUES ('%s', '%s')" % (s_id, b.data['id'])
            res.append(q)
        return res


    #Get a brok, parse it, and return the query for database
    def manage_host_check_result_brok(self, b):
        data = b.data
		
        where_clause = {'host_name' : data['host_name']}
        query = self.create_update_query('host', data, where_clause)

        return [query]


    #Get a brok, parse it, and return the query for database
    def manage_update_host_status_brok(self, b):
        data = b.data

        where_clause = {'host_name' : data['host_name']}
        query = self.create_update_query('host', data, where_clause)

        return [query]
