# standard library imports
import logging, os
import urllib, urllib2, httplib2
import hashlib, json
import time, datetime

from lib.dateutil import parser as DUp

import webapp2

import config
import web.forms as forms
from web.basehandler import BaseHandler
from web.basehandler import user_required, admin_required
from web.models.models import User, Instance, Stream
from lib import slack

# API methods for keeping cloud status and appengine db in sync via fastner box
class InstanceTenderHandler(BaseHandler):
    def get(self):
        try:
            # update list of instances we have
            http = httplib2.Http()
            url = '%s/api/instance/list?token=%s' % (config.fastener_host_url, config.fastener_api_token)

            response, content = http.request(url, 'GET')

            # list of instance from google cloud (see ./fastener/sample-output.json)
            finstances = json.loads(content)

            # list of instances from db
            instances = Instance.get_all()

            # fast fail connection for checking if fusion is up
            http_test = httplib2.Http(timeout=2)

            # loop through list of instances in DB (or local DB if in dev)
            for instance in instances:
                name = instance.name

                for finstance in finstances:
                    if name == finstance['name']:
                        # got a match
                        try:
                            # grab the IP address and status
                            instance.ip = finstance['networkInterfaces'][0]['accessConfigs'][0]['natIP']
                            instance.status = finstance['status']

                            # check if the box is running fusion admin yet
                            try:
                                test_url = 'http://%s:8764' % instance.ip
                                response, content = http_test.request(test_url, 'GET')
                                test_status = response['status']
                            except:
                                test_status = "404"

                            if finstance['status'] == "RUNNING" and test_status == "200":
                                instance.admin_link = test_url
                            else:
                                instance.status = "CONFIGURING"
                                instance.admin_link = None
                                instance.app_link = None

                        except:
                            # got limited data about instance
                            instance.ip = "None"
                            instance.status = finstance['status']
                            instance.admin_link = None
                            instance.app_link = None

                        # instance has been terminated
                        if finstance['status'] == "TERMINATED":
                            pass
                            
                        instance.put()
                        break # no need to keep looking
                else:
                    # no instances were found on Google Cloud for this local instance record
                    if instance.created < datetime.datetime.now() - datetime.timedelta(0, 300):
                        slack.slack_message("DELETING instance %s's record from database. No instance found on Google Cloud." % name)
                        instance.key.delete()
                    else:
                        # only delete if instance create time is greater than 30 minutes...
                        slack.slack_message("WAITING to delete instance %s's record from database. No instance found on Google Cloud." % name)

        except Exception as ex:
            print "yeah, no: %s" % ex
            pass

        return self.render_template('instance/tender.html')


# provide useful link to directly start an instance from another page
class StreamsStarterHandler(BaseHandler):
    @user_required
    def get(self, sid):
        # know the user
        user_info = User.get_by_id(long(self.user_id))

        # check if we have their email
        if not user_info.email:
            self.add_message('Please update your email address before starting an instance!', 'warning')
            return self.redirect_to('account-settings')

        # look up user's instances
        db_instances = Instance.get_all()

        # check the user's limits
        instance_count = 0
        for db_instance in db_instances:
            # limit to instances the user has started
            if db_instance.user == user_info.key:
                instance_count = instance_count + 1

        # warn and redirect if limit is reached
        if (instance_count + 1) > user_info.max_instances:
            self.add_message('Instance limit reached. This account may only start %s instances. Please delete an existing instance to start a new one!' % user_info.max_instances, 'warning')
            return self.redirect_to('instances-list')

        # get stream
        stream = Stream.get_by_sid(sid)

        # make the instance call to the control box
        http = httplib2.Http(timeout=10)
        url = '%s/api/stream/%s?token=%s' % (config.fastener_host_url, sid, config.fastener_api_token)

        # pull the response back TODO add error handling
        response, content = http.request(url, 'POST', None, headers={})
        finstance = json.loads(content)
        name = finstance['instance']

        # set up an instance 
        instance = Instance(
            name = name,
            status = "PROVISIONING",
            user = user_info.key,
            stream = stream.key,
            expires = datetime.datetime.now() + datetime.timedelta(0, 86400), # + 1 day
        )
        instance.put()

        slack.slack_message("Instance type %s created for %s!" % (stream.name, user_info.username))

        # give the db a second to update
        time.sleep(1)

        self.add_message('Instance created! Grab some coffee and wait for %s to start.' % stream.name, 'success')

        params = {'name': name}
        return self.redirect_to('instance-detail', **params)


# list of a user's instances and create new instance
class InstancesListHandler(BaseHandler):
    @user_required
    def get(self, sid=None):
        # lookup user's auth info
        user_info = User.get_by_id(long(self.user_id))

        # redirect to a POST if we have a sid in the URL
        if sid and user_info.email:
            return self.post(sid)

        if not user_info.email or not user_info.name or not user_info.company:
            need_more_info = True
        else:
            need_more_info = False

        # look up user's instances
        db_instances = Instance.get_all()

        # work around index warning/errors using a .filter() in models.py
        instances = []
        for db_instance in db_instances:
            # limit to instances the user has started
            if db_instance.user == user_info.key:
                instances.append(db_instance)

        streams = Stream.get_all()

        params = {
            'instances': instances,
            'num_instances': len(instances),
            'streams': streams,
            'user_id': self.user_id,
            'user_info': user_info,
            'sid': sid,
            'need_more_info': need_more_info
        }

        return self.render_template('instance/list.html', **params)

    @user_required
    def post(self, sid=None):
        # know the user
        user_info = User.get_by_id(long(self.user_id))

        if sid and user_info.email:
            
            # get form values
            stream = Stream.get_by_sid(sid)

            # look up user's instances
            db_instances = Instance.get_all()

            # check the user's limits
            instance_count = 0
            for db_instance in db_instances:
                # limit to instances the user has started
                if db_instance.user == user_info.key:
                    instance_count = instance_count + 1

            # warn and redirect if limit is reached
            if (instance_count + 1) > user_info.max_instances:
                self.add_message('Instance limit reached. This account may only start %s instances. Please delete an existing instance to start a new one!' % user_info.max_instances, 'warning')
                return self.redirect_to('instances-list')

            # make the instance call to the control box
            http = httplib2.Http(timeout=10)
            url = '%s/api/stream/%s?token=%s' % (config.fastener_host_url, sid, config.fastener_api_token)

            # pull the response back TODO add error handling
            response, content = http.request(url, 'POST', None, headers={})
            finstance = json.loads(content)
            name = finstance['instance']

            # set up an instance 
            instance = Instance(
                name = name,
                status = "PROVISIONING",
                user = user_info.key,
                stream = stream.key,
                expires = datetime.datetime.now() + datetime.timedelta(0, 86400), # + 1 day
            )
            instance.put()

            slack.slack_message("Instance type %s created for %s!" % (stream.name, user_info.username))

            # give the db a second to update
            time.sleep(1)

            self.add_message('Instance created! Grab some coffee and wait for %s to start.' % stream.name, 'success')

            params = {'name': name}
            return self.redirect_to('instance-detail', **params)

        else:
            # email update sumbission
            if not self.form.validate():
                self.add_message("There were errors validating your email address.", "error")
                return self.get()

            email = self.form.email.data.strip()

            user_info = User.get_by_id(long(self.user_id))
            user_info.email = email.strip()
            user_info.put()

            self.add_message("Thank you! Your email has been updated.", 'success')
            return self.redirect_to('instances-list')

    @webapp2.cached_property
    def form(self):
        return forms.EmailForm(self)


# instance detail page
class InstanceDetailHandler(BaseHandler):
    @user_required
    def get(self, name):
        # lookup user's auth info
        user_info = User.get_by_id(long(self.user_id))

        # look up user's instances
        instance = Instance.get_by_name(name)

        if not instance:
            params = {}
            return self.redirect_to('instances-list', **params)

        stream = Stream.get_by_id(instance.stream.id())

        params = {
            'instance': instance,
            'stream': stream
        }

        return self.render_template('instance/detail.html', **params)