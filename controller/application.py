#!/usr/bin/env python
#-*- coding:utf-8 -*-

'''
Wiper, an assistant tool for web penetration test.
Copyright (c) 2014-2015 alpha1e0
See the file COPYING for copying detail
'''


import sys
import os
import time
import json
import multiprocessing

from thirdparty import web
from thirdparty import yaml

from lib import formatParam, ParamError, handleException, jsonSuccess, jsonFail
from model.orm import FieldError, ModelError
from model.model import Database, Project, Host, Vul, Comment
from model.dbmanage import DBError
from config import RTD, CONF, WIPError
from plugin.datasave import DataSavePlugin
from plugin.dnsbrute import DnsBrutePlugin
from plugin.googlehacking import GoogleHackingPlugin
from plugin.serviceidentify import ServiceIdentifyPlugin
from plugin.subnetscan import SubnetScanPlugin
from plugin.zonetrans import ZoneTransPlugin


urls = (
    "/", "Index",
    "/install", "Install",
    "/addproject", "ProjectAdd",
    "/listproject", "ProjectList",
    "/getprojectdetail", "ProjectDetail",
    "/deleteproject", "ProjectDelete",
    "/modifyproject", "ProjectModify",
    "/importproject", "ProjectImport",
    "/exportproject", "ProjectExport",
    "/addhost","HostAdd",
    "/listhost","HostList",
    "/gethostdetail","HostDetail",
    "/deletehost","HostDelete",
    "/modifyhost","HostModify",
    "/addvul","VulAdd",
    "/listvul","VulList",
    "/getvuldetail","VulDetail",
    "/deletevul","VulDelete",
    "/modifyvul","VulModify",
    "/addcomment","CommentAdd",
    "/listcomment","CommentList",
    "/getcommentdetail","CommentDetail",
    "/deletecomment","CommentDelete",
    "/modifycomment","CommentModify",
    "/addattachment","AttachmentAdd",
    "/subdomainscan","SubDomianScan",
    "/subnetscan","SubNetScan",
    "/savetmphost","SaveTmpHost",
    "/deletetmphost","DeleteTmpHost",
    "/servicerecognize","ServiceRecognize",
    "/dbsetup","DBSetup",
    "/adddict","DictAdd",
    "/nmapsetup","NmapSetup"
)


server = web.application(urls, globals())
application = server.wsgifunc()


# ================================================index page=========================================

class Index(object):
    def GET(self):
        render = web.template.render('view')
        if not CONF.isinstall:
            return render.install()
        else:
            return render.index()


class Install(object):
    def GET(self):
        render = web.template.render('view')
        if CONF.isinstall:
            return render.index()
        else:
            return render.install()

    def POST(self):
        originParams = web.input()
        options = (
            ("dbname","string","1-50"),
        )

        if not os.path.exists("log"):
            os.mkdir("log")
        if not os.path.exists(os.path.join("static","attachment")):
            os.mkdir(os.path.join("static","attachment"))
        if not os.path.exists(os.path.join("static","tmp")):
            os.mkdir(os.path.join("static","tmp"))
        if not os.path.exists("data"):
            os.mkdir("data")
        if not os.path.exists(os.path.join("data","database")):
            os.mkdir(os.path.join("data","database"))

        try:
            params = formatParam(originParams, options)
        except ParamError as error:
            raise web.internalerror("Parameter error, {0}.".format(error))

        try:
            CONF.db.name = str(params.dbname)
        except WIPError as error:
            raise web.internalerror("Configure file parse error.")

        try:
            Database.create()
        except DBError as error:
            raise web.internalerror("Databae creating error,"+str(error))

        CONF.isinstall = True
        CONF.save()

        return jsonSuccess()


# ================================the operation of project=========================================
class ProjectList(object):
    @handleException
    def GET(self):
        params = web.input()
        result = Project.orderby(params.orderby.strip()).getsraw("id","name","level")
        return json.dumps(result)


class ProjectDetail(object):
    @handleException
    def GET(self):
        params = web.input()
        project = Project.get(params.id)
        return project.toJson()


class ProjectAdd(object):
    @handleException
    def POST(self):
        params = web.input()
        kw = {k:params[k].strip() for k in ("name","url","ip","level","whois","description")}
        project = Project(**kw)
        project.save()
        return jsonSuccess()


class ProjectDelete(object):
    def GET(self):
        params = web.input()
        if not params.id.strip().isdigit():
            raise web.internalerror("Parameter type error.")

        project = Project.get(params.id.strip())
        hosts = Host.where(project_id=project.id).gets("id")
        for host in hosts:
            vuls = Vul.where(host_id=host.id).gets("id")
            for vul in vuls:
                vul.remove()

            comments = Comment.where(host_id=host.id).gets("id")
            for comment in comments:
                comment.remove()

            host.remove()

        project.remove()

        return jsonSuccess()


class ProjectModify(object):
    @handleException
    def POST(self):
        params = web.input()
        kw = {k:params[k].strip() for k in ("name","url","ip","whois","description","level")}
        Project.where(id=params.id.strip()).update(**kw)
        return jsonSuccess()
        

class ProjectImport(object):
    def POST(self):
        web.header('Content-Type', 'application/json')
        params = web.input(projectfile={})
        try:
            fileName = params.projectfile.filename
            fileStr = params.projectfile.value
        except AttributeError:
            raise web.internalerror("Missing parameter.")
        
        projectDict = json.loads(fileStr)
        hosts = projectDict.get("hosts",[])
        try:
            del projectDict['hosts']
        except KeyError:
            pass
        try:
            Project(**projectDict).save()
        except DBError as error:
            raise web.internalerror("failed to insert project "+str(error))
        projectid = Project.where(name=projectDict.get('name')).getsraw('id')[0]['id']

        for host in hosts:
            vuls = host.get("vuls",[])
            comments = host.get("comments",[])
            try:
                del host['vuls']
                del host['comments']
            except KeyError:
                pass
            host['project_id'] = projectid
            Host(**host).save()
            kwargs = {key:host[key] for key in ['url','ip','port'] if key in host}
            hostid = Host.where(**kwargs).getsraw('id')[0]['id']

            for vul in vuls:
                vul['host_id'] = hostid
                Vul(**vul).save()
            for comment in comments:
                comment['host_id'] = hostid
                Comment(**comment).save()

        return jsonSuccess()


class ProjectExport(object):
    def GET(self):
        params = web.input()
        try:
            projectid = int(params.id)
        except (ValueError, AttributeError):
            raise web.internalerror("parameter error.")

        project = Project.getraw(projectid)
        if project:
            hosts = Host.where(project_id=projectid,tmp=0).getsraw()
            
            for host in hosts:
                host['vuls'] = Vul.where(host_id=host['id']).getsraw('name','url','info','type','level','description')
                host['comments'] = Comment.where(host_id=host['id']).getsraw('name','url','info','level','description')
                del host['id']
                del host['tmp']
                del host['project_id']
            project['hosts'] = hosts
            del project['id']

        projectName = "_".join(project['name'].split(" "))
        projectFile = os.path.join("static","tmp",projectName+".proj")

        try:
            with open(projectFile,'w') as fd:
                json.dump(project, fd)
        except IOError:
            raise web.internalerror("save imported project failed")


#=================================the operation of host=========================================

class HostList(object):
    @handleException
    def GET(self):
        params = web.input()
        result = Host.where(project_id=params.projectid.strip(),tmp=0).orderby(params.orderby.strip()).getsraw('id','title','url','ip','level','protocol')
        return json.dumps(result)


class HostDetail(object):
    @handleException
    def GET(self):
        params = web.input()
        result = Host.getraw(params.id)
        return json.dumps(result)


class HostAdd(object):
    @handleException
    def POST(self):
        params = web.input()
        kw = {k:params[k].strip() for k in ("title","url","ip","port","protocol","level","os","server_info","middleware","description","project_id")}
        Host.insert(**kw)
        return jsonSuccess()


class HostDelete(object):
    def GET(self):
        params = web.input()
        if not params.id.strip().isdigit():
            raise web.internalerror("Parameter type error.")

        host = Host.get(params.id.strip())
        vuls = Vul.where(host_id=host.id).gets("id")
        for vul in vuls:
            vul.remove()

        comments = Comment.where(host_id=host.id).gets("id")
        for comment in comments:
            comment.remove()

        host.remove()

        return jsonSuccess()


class HostModify(object):
    @handleException
    def POST(self):
        params = web.input()
        kw = {k:params[k].strip() for k in ("title","url","ip","port","protocol","level","os","server_info","middleware","description")}
        Host.where(id=params.id.strip()).update(**kw)
        return jsonSuccess()


#=================================the operation of vul=========================================

class VulList(object):
    @handleException
    def GET(self):
        params = web.input()
        result = Vul.where(host_id=params.hostid.strip()).orderby(params.orderby.strip()).getsraw('id','name','level')
        return json.dumps(result)


class VulDetail(object):
    @handleException
    def GET(self):
        params = web.input()
        result = Vul.getraw(params.id)
        return json.dumps(result)


class VulAdd(object):
    @handleException
    def POST(self):
        params = web.input()
        kw = {k:params[k].strip() for k in ("name","url","info","type","level","description","host_id")}
        Vul.insert(**kw)
        return jsonSuccess()


class VulDelete(object):
    @handleException
    def GET(self):
        params = web.input()
        Vul.delete(params.id.strip())
        return jsonSuccess()


class VulModify(object):
    @handleException
    def POST(self):
        params = web.input()
        kw = {k:params[k].strip() for k in ("id","name","url","info","type","level","description")}
        Vul.where(id=params.id.strip()).update(**kw)
        return jsonSuccess()


#=================================the operation of comment=========================================

class CommentList(object):
    @handleException
    def GET(self):
        params = web.input()
        result = Comment.where(host_id=params.hostid.strip()).orderby(params.orderby.strip()).getsraw('id','name','level')
        return json.dumps(result)       


class CommentDetail(object):
    @handleException
    def GET(self):
        params = web.input()
        result = Comment.getraw(params.id)
        return json.dumps(result)


class CommentAdd(object):
    @handleException
    def POST(self):
        params = web.input()
        kw = {k:params[k].strip() for k in ("name","url","info","level","description","host_id")}
        Comment.insert(**kw)
        return jsonSuccess()


class CommentDelete(object):
    def GET(self):
        params = web.input()

        try:
            comment = Comment.get(params.id.strip())
        except AttributeError:
            raise web.internalerror("Missing parameter.")
        except FieldError as error:
            raise web.internalerror(error)
        except WIPError as error:
            RTD.log.error(error)
            raise web.internalerror("Internal ERROR!")

        if not comment:
            return jsonFail()

        #delete attachment
        if comment.attachment:
            if os.path.exists(os.path.join("static","attachment",comment.attachment)):
                os.remove(os.path.join("static","attachment",comment.attachment))

        comment.remove()

        return jsonSuccess()


class CommentModify(object):
    @handleException
    def POST(self):
        params = web.input()
        kw = {k:params[k].strip() for k in ("id","name","url","info","level","description")}
        Comment.where(id=params.id.strip()).update(**kw)
        return jsonSuccess()


class AttachmentAdd(object):
    def POST(self):
        originParams = web.input(attachment={})
        originParams["filename"] = originParams.attachment.filename
        originParams["value"] = originParams.attachment.value

        options = (
            ("hostid","integer","0-0"),
            ("filename","string","1-200"),
            ("name","string","0-200"),
            ("value","text","")
        )

        try:
            params = formatParam(originParams, options)
        except ParamError as error:
            raise web.internalerror("Parameter error, {0}.".format(error))
            

        hostID = params.hostid
        attachName = params.name
        attachFilename = params.filename
        fileCTime = time.strftime("%Y-%m-%d-%H%M%S",time.localtime())
        fileNamePrefix = "{0}_{1}".format(hostID,fileCTime)
        if attachName != "":
            attachType = os.path.splitext(attachFilename)[-1]
            fileName = u"{0}_{1}{2}".format(fileNamePrefix,attachName,attachType)
        else:
            fileName = u"{0}_{1}".format(fileNamePrefix,attachFilename)
        fileNameFull = os.path.join("static","attachment",fileName)

        try:
            comment = Comment(name=fileName,url="",info="",level=3,attachment=fileName,description="attachment:"+fileName,host_id=hostID)
        except WIPError as error:
            RTD.log.error(error)
            raise web.internalerror("Internal ERROR!")

        try:
            fd = open(fileNameFull, "wb")
            fd.write(params.value)
        except IOError as error:
            raise web.internalerror('Write attachment file failed!')
        finally:
            fd.close()

        try:
            comment.save()
        except FieldError as error:
            RTD.log.error(error)
            raise web.internalerror(error)
        except WIPError as error:
            RTD.log.error(error)
            raise web.internalerror("Internal ERROR!")

        return True


#=================================operation of autotask=========================================

class SubDomianScan(object):
    def GET(self):
        web.header('Content-Type', 'application/json')

        result = os.listdir(os.path.join("data","wordlist","dnsbrute"))
        return json.dumps(result)

    def POST(self):
        web.header('Content-Type', 'application/json')
        params = web.input()
        rawParam = web.data()

        try:
            projectid = int(params.project_id)
        except AttributeError as error:
            RTD.log.error(error)
            raise web.internalerror(error)

        rawParamList = [x.split("=") for x in rawParam.split("&")]
        dictList = [x[1] for x in rawParamList if x[0]=="dictlist"]

        options = (
            ("domain","url",""),
        )
        try:
            domainParams = formatParam(params, options)
        except ParamError as error:
            raise web.internalerror("Parameter error, {0}.".format(error))

        initQueue = multiprocessing.Queue()
        domainQueue = multiprocessing.Queue()
        saveQueue = multiprocessing.Queue()

        domainTask = []
        if "dnsbrute" in params.keys():
            domainTask.append(DnsBrutePlugin(dictList, inqueue=initQueue, 
                outqueue=domainQueue))
        if "googlehacking" in params.keys():
            domainTask.append(GoogleHackingPlugin(inqueue=initQueue, 
                outqueue=domainQueue))
        if "zonetrans" in params.keys():
            domainTask.append(ZoneTransPlugin(inqueue=initQueue, 
                outqueue=domainQueue))
        if not domainTask:
            domainTask = [GoogleHackingPlugin(inqueue=initQueue, 
                outqueue=domainQueue)]

        serviceIdTask = ServiceIdentifyPlugin(inqueue=domainQueue, 
            outqueue=saveQueue, stopcount=len(domainTask))

        saveTask = DataSavePlugin(projectid=projectid, inqueue=saveQueue)

        host = dict(url=domainParams.domain)
        initQueue.put(host)
        initQueue.put(saveTask.STOP_LABEL)

        for task in domainTask:
            task.start()
        serviceIdTask.start()
        saveTask.start()

        return jsonSuccess()


class SubNetScan(object):
    def getIPList(self, projectid):
        try:
            hosts = Host.where(project_id=projectid).getsraw("ip")
        except (KeyError, AttributeError, FieldError, ModelError, DBError) as error:
            RTD.log.error(error)
            raise web.internalerror(error)
        
        result = list()
        for host in hosts:
            try:
                pos = host['ip'].rindex(".")
                ip = host['ip'][:pos] + ".1"
            except (KeyError, ValueError, AttributeError):
                continue
            for key in result:
                if ip == key[0]:
                    key[1] += 1
                    break
            else:
                result.append([ip,1])

        return result

    def GET(self):
        web.header('Content-Type', 'application/json')
        params = web.input()

        try:
            projectid = int(params.project_id)
        except AttributeError as error:
            RTD.log.error(error)
            raise web.internalerror(error)

        iplist = self.getIPList(projectid)
        hosts = Host.where(project_id=projectid, tmp=1).orderby("ip").getsraw('id','title','ip','port','protocol')

        result = {'iplist':iplist, 'hosts':hosts}

        return json.dumps(result)

    def POST(self):
        web.header('Content-Type', 'application/json')
        params = web.input()
        rawParam = web.data()

        try:
            projectid = int(params.project_id)
        except AttributeError as error:
            RTD.log.error(error)
            raise web.internalerror(error)

        rawParamList = [x.split("=") for x in rawParam.split("&")]
        ipList = [x[1] for x in rawParamList if x[0]=="iplist"]

        hosts = [dict(ip=x) for x in ipList]
        defaultValue = {"tmp":1}

        initQueue = multiprocessing.Queue()
        domainQueue = multiprocessing.Queue()
        saveQueue = multiprocessing.Queue()

        subnetTask = SubnetScanPlugin(inqueue=initQueue, outqueue=domainQueue)
        serviceIdTask = ServiceIdentifyPlugin(ptype=1, inqueue=domainQueue, 
            outqueue=saveQueue)
        saveTask = DataSavePlugin(defaultValue=defaultValue, 
            projectid=projectid, inqueue=saveQueue)

        for host in hosts:
            initQueue.put(host)
        initQueue.put(saveTask.STOP_LABEL)

        subnetTask.start()
        serviceIdTask.start()
        saveTask.start()

        return jsonSuccess()


class SaveTmpHost(object):
    def GET(self):
        web.header('Content-Type', 'application/json')
        params = web.input()

        try:
            hid = str(int(params.id))
        except AttributeError as error:
            RTD.log.error(error)
            raise web.internalerror(error)

        try:
            host = Host.get(hid)
            host.tmp = 0
            host.save(update=True)
        except (KeyError, AttributeError, FieldError, ModelError, DBError) as error:
            RTD.log.error(error)
            raise web.internalerror(error)

        return jsonSuccess()


class DeleteTmpHost(object):
    def GET(self):
        web.header('Content-Type', 'application/json')
        params = web.input()

        try:
            hid = str(int(params.id))
        except AttributeError as error:
            RTD.log.error(error)
            raise web.internalerror(error)

        try:
            Host.delete(hid)
        except (KeyError, AttributeError, FieldError, ModelError, DBError) as error:
            RTD.log.error(error)
            raise web.internalerror(error)

        return jsonSuccess()


class ServiceRecognize(object):
    def POST(self):
        web.header('Content-Type', 'application/json')
        originParams = web.input()

        options = (
            ("domain","string","1-200"),
            ("type","integer","0-3"),
            ("project_id","integer","")
        )
        try:
            params = formatParam(originParams, options)
        except ParamError as error:
            raise web.internalerror("Parameter error, {0}.".format(error))

        domain = params.domain.lower()
        protocol = ""
        port = None

        #resolve protocol
        if domain.startswith("http://"):
            protocol = "http"
            domain = domain[7:]
            port = 80
        elif domain.startswith("https://"):
            protocol = "https"
            domain = domain[8:]
            port = 443
        elif "://" in domain:
            raise web.internalerror("unrecognized protocol, should be 'http' or 'https'.")
        #resolve port
        try:
            pos = domain.rindex(":")
        except ValueError:
            pass
        else:
            try:
                port = int(domain[pos+1:])
            except ValueError:
                pass
            domain = domain[:pos]

        if not protocol: protocol = "http"
        if not port: port = 80

        initQueue = multiprocessing.Queue()
        saveQueue = multiprocessing.Queue()

        serviceIdTask = ServiceIdentifyPlugin(ptype=int(params.type), 
            inqueue=initQueue, outqueue=saveQueue)
        saveTask = DataSavePlugin(projectid=params.project_id, 
            inqueue=saveQueue)

        host = dict(url=domain,protocol=protocol,port=port)
        initQueue.put(host)
        initQueue.put(saveTask.STOP_LABEL)

        serviceIdTask.start()
        saveTask.start()

        return jsonSuccess()


class DBSetup(object):
    def GET(self):
        web.header('Content-Type', 'application/json')

        alldbs = os.listdir(os.path.join("data","database"))
        currentdb = CONF.db.name

        return json.dumps({'all':alldbs,'current':currentdb})

    def POST(self):
        web.header('Content-Type', 'application/json')
        originParams = web.input()

        options = (
            ("database","string","1-50"),
        )
        try:
            params = formatParam(originParams, options)
        except ParamError as error:
            raise web.internalerror("Parameter error, {0}.".format(error))

        oldDB = CONF.db.name
        CONF.db.name = str(params.database)
        dblist = os.listdir(os.path.join("data","database"))
        if params.database not in dblist:
            try:
                Database.create()
            except DBError as error:
                CONF.db.name = oldDB
                raise web.internalerror("Databae creating error,"+str(error))
        CONF.save()

        return jsonSuccess()


class DictAdd(object):
    def POST(self):
        web.header('Content-Type', 'application/json')
        params = web.input(dictfile={})

        try:
            fileName = params.dictfile.filename
            dtype = int(params.type)
        except AttributeError:
            raise web.internalerror("Missing parameter.")
        if dtype == 0:
            fileNameFull = os.path.join("data","wordlist","dnsbrute",fileName)
        else:
            raise web.internalerror("dict type error.")

        try:
            fd = open(fileNameFull, "w")
            fd.write(params.dictfile.value)
        except IOError as error:
            raise web.internalerror('Write dictfile failed!')

        return jsonSuccess()


class NmapSetup(object):
    def POST(self):
        originParams = web.input()

        options = (
            ("nmappath","string","1-200"),
        )
        try:
            params = formatParam(originParams, options)
        except ParamError as error:
            raise web.internalerror("Parameter error, {0}.".format(error))

        CONF.nmap = None if str(params.nmappath)=="nmap" else str(params.nmappath)
        CONF.save()

        return jsonSuccess()

