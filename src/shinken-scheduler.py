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


#For the Shinken application, I try to respect
#The Zen of Python, by Tim Peters. It's just some
#very goods ideas that make Python programming very fun
#and efficient. If it's good for Python, it must be good for
#Shinken. :)
#
#
#
#Beautiful is better than ugly.
#Explicit is better than implicit.
#Simple is better than complex.
#Complex is better than complicated.
#Flat is better than nested.
#Sparse is better than dense.
#Readability counts.
#Special cases aren't special enough to break the rules.
#Although practicality beats purity.
#Errors should never pass silently.
#Unless explicitly silenced.
#In the face of ambiguity, refuse the temptation to guess.
#There should be one-- and preferably only one --obvious way to do it.
#Although that way may not be obvious at first unless you're Dutch.
#Now is better than never.
#Although never is often better than *right* now.
#If the implementation is hard to explain, it's a bad idea.
#If the implementation is easy to explain, it may be a good idea.
#Namespaces are one honking great idea -- let's do more of those!


#This class is the app for scheduling
#it create the scheduling object after listen for arbiter
#for a conf. It listen for arbiter even after the scheduler is launch.
#if a new conf is received, the scheduler is stopped
#and a new one is created.
#The scheduler create list of checks and actions for poller
#and reactionner.
#import os
#import re
import time
import sys
import Pyro.core
#import signal
import select
import random

from check import Check
#from util import get_sequence
from scheduler import Scheduler
from config import Config
from macroresolver import MacroResolver
from external_command import ExternalCommand



#Interface for Workers
#They connect here and see if they are still OK with
#our running_id, if not, they must drop their checks
#in progress
class IChecks(Pyro.core.ObjBase):
	#we keep sched link
	#and we create a running_id so poller and
	#reactionner know if we restart or not
	def __init__(self, sched):
                Pyro.core.ObjBase.__init__(self)
		self.sched = sched
		self.running_id = random.random()


	#poller or reactionner is asking us our running_id
	def get_running_id(self):
		return self.running_id

		
	#poller or reactionner ask us actions
        def get_checks(self , do_checks=False, do_actions=False):
		#print "We ask us checks"
		res = self.sched.get_to_run_checks(do_checks, do_actions)
		#print "Sending %d checks" % len(res)
		self.sched.nb_checks_send += len(res)
		return res

	
	#poller or reactionner are putting us results
	def put_results(self, results):
		for c in results:
			self.sched.put_results(c)



#Interface for Brokers
#They connect here and get all broks (data for brokers)
#datas must be ORDERED! (initial status BEFORE uodate...)
class IBroks(Pyro.core.ObjBase):
	#we keep sched link
	def __init__(self, sched):
                Pyro.core.ObjBase.__init__(self)
		self.sched = sched
		self.running_id = random.random()


	#Broker need to void it's broks?
	def get_running_id(self):
		return self.running_id

		
	#poller or reactionner ask us actions
	def get_broks(self):
		#print "We ask us broks"
		res = self.sched.get_broks()
		#print "Sending %d broks" % len(res)#, res
		self.sched.nb_broks_send += len(res)
		return res


	#Ping? Pong!
	def ping(self):
		return None


#Interface for Arbiter, our big MASTER
#We ask him a conf and after we listen for him.
#HE got user entry, so we must listen him carefully
#and give information he want, maybe for another scheduler
class IForArbiter(Pyro.core.ObjBase):
	def __init__(self, app):
                Pyro.core.ObjBase.__init__(self)
		self.app = app
		self.running_id = random.random()

	#verry usefull?
	def get_running_id(self):
		return self.running_id


	#use full too?
	def get_info(self, type, ref, prop, other):
		return self.app.sched.get_info(type, ref, prop, other)


	#arbiter is send us a external coomand.
	#it can send us global command, or specific ones
	def run_external_command(self, command):
		self.app.sched.run_external_command(command)


	#Arbiter is sending us a new conf. Ok, we take it, and if
	#app has a scheduler, we ask it to die, so the new conf 
	#will be load, and a new scheduler created
	def put_conf(self, conf):
		self.app.conf = conf#cPickle.loads(conf)
		print "Get conf:", self.app.conf
		self.app.have_conf = True
		print "Have conf?", self.app.have_conf

		print "Just apres reception"
                #from guppy import hpy
                #hp=hpy()
                #print hp.heap()
                #print hp.heapu()

		
                #if app already have a scheduler, we must say him to 
                #DIE Mouahahah
		#So It will quit, and will load a new conf (and create a brand new scheduler)
		if hasattr(self.app, "sched"):
			self.app.sched.die()
			

	#Arbiter want to know if we are alive
	def ping(self):
		return True

	#Use by arbiter to know if we have a conf or not
	#can be usefull if we must do nothing but 
	#we are not because it can KILL US! 
	def have_conf(self):
		return self.app.have_conf


	#Call by arbiter if it thinks we are running but we must do not (like
	#if I was a spare that take a conf but the master returns, I must die
	#and wait a new conf)
	#Us : No please...
	#Arbiter : I don't care, hasta la vista baby!
	#Us : ... <- Nothing! We are die! you don't follow 
	#anything or what??
	def wait_new_conf(self):
		print "Arbiter want me to wait a new conf"
		self.app.have_conf = False
		if hasattr(self.app, "sched"):
                        self.app.sched.die()


#Tha main app class
class Shinken:
	default_port = 7768

	#Create the shinken class:
	#Create a Pyro server (port = arvg 1)
	#then create the interface for arbiter
	#Then, it wait for a first configuration
	def __init__(self):
		#create the server
		Pyro.config.PYRO_COMPRESSION = 1
		Pyro.config.PYRO_MULTITHREADED = 0
		Pyro.core.initServer()
	
		if len(sys.argv) == 2:
			self.port = int(sys.argv[1])
		else:
			self.port = self.__class__.default_port
		print "Port:", self.port
		self.poller_daemon = Pyro.core.Daemon(port=self.port)
		if self.poller_daemon.port != self.port:
			print "Sorry, the port %d is not free" % self.port
			sys.exit(1)

		#Now the interface
		i_for_arbiter = IForArbiter(self)
		self.uri2 = self.poller_daemon.connect(i_for_arbiter,"ForArbiter")
		print "The daemon runs on port:", self.poller_daemon.port
		print "The arbiter daemon runs on port:", self.poller_daemon.port
		print "The object's uri2 is:", self.uri2
		
		#Ok, now the conf
		self.must_run = True
		self.wait_initial_conf()
		print "Ok we've got conf"
		

	#We wait (block) for arbiter to send us conf
	def wait_initial_conf(self):
		self.have_conf = False
		print "Waiting for initial configuration"
		timeout = 1.0
		while not self.have_conf :
			socks = self.poller_daemon.getServerSockets()
			avant = time.time()
			# 'foreign' event loop
			ins,outs,exs = select.select(socks,[],[],timeout)
			if ins != []:
				for s in socks:
					if s in ins:
						self.poller_daemon.handleRequests()
						print "Apres handle : Have conf?", self.have_conf
						apres = time.time()
						diff = apres-avant
						timeout = timeout - diff
						break    # no need to continue with the for loop
			else: #Timeou
				sys.stdout.write(".")
				sys.stdout.flush()
				timeout = 1.0

			if timeout < 0:
				timeout = 1.0


	#OK, we've got the conf, now we load it
	#and launch scheduler with it
	#we also create interface for poller and reactionner
	def load_conf(self):
		#create scheduler with ref of our daemon
		self.sched = Scheduler(self.poller_daemon)
		#give it an interface
		self.uri = self.poller_daemon.connect(IChecks(self.sched),"Checks")
		print "The object's uri is:",self.uri
		
		self.uri2 = self.poller_daemon.connect(IBroks(self.sched),"Broks")
		print "The object's uri2 is:",self.uri2

		print "Loading configuration"
		self.conf.explode_global_conf()
		self.conf.is_correct()
		#Creating the Macroresolver Class & unique instance
		m = MacroResolver()
		m.init(self.conf)
		#we give sched it's conf
		self.sched.load_conf(self.conf)
		
		#Now create the external commander
		#it's a applyer : it role is not to dispatch commands,
		#but to apply them
		e = ExternalCommand(self.conf, 'applyer')

		#Scheduler need to know about external command to 
		#activate it if necessery
		self.sched.load_external_command(e)
		
		#External command need the sched because he can raise checks
		e.load_scheduler(self.sched)


	#our main function, launch after the init
	def main(self):
		#ok, if we are here, we've got the conf
		self.load_conf()
		
		print "Configuration Loaded"
		while self.must_run:
			self.sched.run()
                        #Ok, we quit scheduler, but maybe it's just for
			#reloading our configuration
			if self.must_run:
				if self.have_conf:
					self.load_conf()
				else:
					self.wait_initial_conf()
					self.load_conf()
				


#Here we go!
if __name__ == '__main__':
	p = Shinken()
        import cProfile
	#p.main()
        command = """p.main()"""
        cProfile.runctx( command, globals(), locals(), filename="var/Shinken.profile" )
