#!/usr/bin/env python
 
# you'll need to populate the following three
cluster_user = "admin"
cluster_pass = "admin"
clusters = [ "cluster01", "cluster02", "10.99.34.25", ... ]
 
# What follows is an abbreviated version of our Nutanix python module, built
# upon on a poc backup script from gasmith@nutanix.com
# The rest of the script continues below.
import json
import requests
import urllib
import re
 
class VMNotFound(Exception):
    """
   Indicates the given VM was not found on this cluster
   """
    pass
 
class VMNotUnique(Exception):
    """
   Indicates the given VM name is not unique on this cluster
   """
    pass
 
class RESTException(Exception):
    """
   Indicates the given REST request (GET/POST/PUT, etc) failed
   """
    pass
 
class NutanixException(Exception):
    """
   Indicates the requested Nutanix operation failed
   """
    pass
 
class Nutanix():
 
    def __init__(self, cluster_ip, username, password):
        """
       Initializes the server session
       """
        self.cluster_ip    = cluster_ip
        self.username      = username
        self.password      = password
        self.base_acro_url = "https://{!s}:9440/api/nutanix/v0.8".format(self.cluster_ip)
        self.base_pg_url   = "https://{!s}:9440/PrismGateway/services/rest/v1".format(self.cluster_ip)
        self.session       = self.get_server_session(self.username, self.password)
 
    def get_server_session(self, username, password):
        """
       Creating REST client session for server connection, after globally setting
       Authorization, Content-Type and charset for session.
       """
        session = requests.Session()
        session.auth = (username, password)
        session.verify = False
        session.headers.update(
            {'Content-Type': 'application/json; charset=utf-8'})
        return session
 
    def _url(self, base, path, params):
        """
       Helper method to generate a URL from a base, relative path, and dictionary
       of query parameters.
       """
        if params:
            return "{!s}/{!s}?{!s}".format(base, path, urllib.urlencode(params))
        else:
            return "{!s}/{!s}".format(base, path)
 
    def acro_url(self, path, **params):
        """
       Helper method to generate an Acropolis interface URL.
       """
        return self._url(self.base_acro_url, path, params)
 
    def pg_url(self, path, **params):
        """
       Helper method to generate an Prism Gateway interface URL.
       """
        return self._url(self.base_pg_url, path, params)
 
    def get_vms(self, name=None, name_re=None):
        """
       Fetches the defined vms.
       """
        if name_re and name:
            raise Exception("Cannot specify name_re and name parameters to get_vms")
 
        # Use the prism gateway interface to grab the list of vms
        if name:
            url = self.pg_url("vms", filterCriteria="vm_name=={}".format(name))
        else:
            url = self.pg_url("vms")
 
        r = self.session.get(url)
        if r.status_code != requests.codes.ok:
            raise RESTException("GET {!s}: {!s}".format(url, r.status_code))
 
        res = [ x for x in r.json()['entities'] if 'nonNdfsDetails' not in x or x['nonNdfsDetails'] != 'VM is a Nutanix CVM' ]
 
        if name_re:
            return [ x for x in res if re.search(name_re, x['vmName']) ]
 
        return res
 
    def get_host(self, id):
        """
       Fetches the host/hypervisor with the given id.
       """
 
        # Use the prism gateway interface to grab the host
        url = self.pg_url("hosts/{}".format(id))
 
        r = self.session.get(url)
        if r.status_code != requests.codes.ok:
            raise RESTException("GET {!s}: {!s}".format(url, r.status_code))
 
        res = r.json()
        return res
 
    def poll_task(self, task_uuid):
        """
       Polls a task until it completes. Fails if the task completes with an error.
       """
        url = self.acro_url("tasks/{!s}/poll".format(task_uuid))
        while True:
            print("Polling task {!s} for completion".format(task_uuid))
            r = self.session.get(url)
            if r.status_code != requests.codes.ok:
                raise RESTException("GET {!s}: {!s}".format(url, r.status_code))
 
            task_info = r.json()["taskInfo"]
            mr = task_info.get("metaResponse")
            if mr is None:
                continue
            if mr["error"] == "kNoError":
                break
            else:
                raise NutanixException("Task {!s} failed: {!s}: {!s}".format(task_uuid, mr["error"], mr["errorDetail"]))
# End of abbreviated Nutanix utility module
 
# This presumes you have a consistent user/pass you can use across these
# clusters. If not, you'll need to adjust this accordingly.
cluster_handles = [ Nutanix(x, cluster_user, cluster_pass) for x in clusters ]
 
def find_vm(vm):
    """
   Returns a tuple of the JSON describing the requested VM and a Nutanix
   object authenticated to the cluster housing it. Raises an exception if
   more than one VM is found with the given name.
   """
    for cluster in cluster_handles:
        vms = cluster.get_vms(name=vm)
        if len(vms) == 1:
            return vms[0], cluster
        elif len(vms) > 1:
            # this is probably bad
            raise Exception("More than one ({}) vm matching name {} found on cluster {}".format(len(vms), vm, cluster.cluster_ip))
 
if __name__ == "__main__":
    import sys
 
    if len(sys.argv) != 2:
        print "Usage: {} VM_NAME".format(sys.argv[0].split("/")[-1])
        print
        print "Finds the host (hypervisor) that VM_NAME is running on and returns"
        print "its name, ip, and the external ip of its service VM."
        sys.exit(1)
 
    vm, cluster_handle = find_vm(sys.argv[1])
    # the hostId field is of format CLUSTER_UUID::HOST_ID
    host_id = vm["hostId"].split(":", 2)[2]
    host = cluster_handle.get_host(host_id)
 
    host_name = host["name"]
    host_addr = host["hypervisorAddress"]
    host_svm = host["serviceVMExternalIP"]
    print "Name        : {}".format(host_name)
    print "Address     : {}".format(host_addr)
    print "SVM Address : {}".format(host_svm)
