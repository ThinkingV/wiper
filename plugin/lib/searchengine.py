#!/usr/bin/env python
#-*- coding:utf-8 -*-

'''
Wiper, an assistant tool for web penetration test.
Copyright (c) 2014-2015 alpha1e0
See the file COPYING for copying detail
'''

import os
import random
import time

from thirdparty import requests
from thirdparty.requests.packages.urllib3.exceptions import InsecureRequestWarning
from thirdparty.requests.packages.urllib3 import disable_warnings
from thirdparty import yaml
from thirdparty.BeautifulSoup import BeautifulSoup
from config import Dict


disable_warnings(InsecureRequestWarning)


class SearchEngineError(Exception):
    def __init__(self, reason=""):
        self.errMsg = "SearchEngineError. " + ("reason: "+reason if reason else "")

    def __str__(self):
        return self.errMsg


class SearchConfig(object):
    def __new__(cls, engine):
        configFile = os.path.join("plugin","config","searchengine.yaml")
        try:
            with open(configFile, "r") as fd:
                config = yaml.load(fd)[engine]
        except IOError:
            raise SearchEngineError("read searchengine configuration file 'searchengine.yaml' failed")
        else:
            return config


class UserAgents(object):
    def __new__(cls):
        configFile = os.path.join("plugin","config","useragent.yaml")
        try:
            with open(configFile, "r") as fd:
                config = yaml.load(fd)
        except IOError:
            userAgents = ["Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)",
                "Mozilla/5.0 (Windows; U; Windows NT 5.2)Gecko/2008070208 Firefox/3.0.1",
                "Opera/9.27 (Windows NT 5.2; U; zh-cn)",
                "Mozilla/5.0 (Macintosh; PPC Mac OS X; U; en)Opera 8.0)"]
        else:
            userAgents = [x['User-Agent'] for x in config]

        return userAgents


class Query(object):
    '''
    Build query keyword
    input:
        site: seach specified site
        title: search in title
        url: search in url
        filetype: search files with specified file type
        link: search in link
        kw: raw keywords to search 
    example:
        query = Query(site="xxx.com") | -Query(site="www.xxx.com") | Query(kw="password")
        query.doSearch(engine="baidu")
    '''
    def __init__(self, **kwargs):
        # _qlist record the query value, format [-/+, key, value]
        self._qlist = list()
        self.queryResult = list()

        keylist = ['site','title','url','filetype','link','kw']
        for key,value in kwargs.iteritems():
            if key not in keylist:
                self._qlist.append(["",'kw',value])
            self._qlist.append(["",key,value])


    def __neg__(self):
        self._qlist[0][0] = "-"
        return self

    def __pos__(self):
        self._qlist[0][0] = "+"
        return self

    def __or__(self, obj):
        self._qlist += obj._qlist
        return self


    def genKeyword(self, engine):
        '''
        Generate keyword string.
        '''
        config = SearchConfig(engine)
        keyword = ""
        for line in self._qlist:
            if line[1] in config['ghsyn']:
                if config['ghsyn'][line[1]]:
                    keyword += line[0] + config['ghsyn'][line[1]] + ":" + line[2] + " "
                else:
                    keyword += line[0] + line[2] + " "
            elif line[1] == "kw":
                keyword += line[0] + line[2] + " "

        return keyword.strip()


    def doSearch(self, engine="baidu", size=500):
        '''
        Search in search engine.
        '''
        keyword = self.genKeyword(engine)
        if engine == "baidu":
            baidu = Baidu(size=size)
            return baidu.search(keyword)
        elif engine == "bing":
            bing = Bing(size=size)
            return bing.search(keyword)
        elif engine == "google":
            google = Google(size=size)
            return google.search(keyword)
        else:
            return None


class SearchEngine(object):
    '''
    Base searchengine class.
    input:
        size: specified the amount of the result
        engine: the engine name
    '''
    def __init__(self, engine, size=200):
        self.size = size
        self.retry = 20
        self.config = SearchConfig(engine)
        self.userAgents = UserAgents()

        self.url = self.config['url']
        self.defaultParam = dict(**self.config['default'])

        #this signature string illustrate the searchengine find something, should be redefined in subclass
        self.findSignature = ""
        #this signature string illustrate the searchengine find nothing, should be redefined in subclass
        self.notFindSignature = ""


    def search(self, keyword, size=None):
        '''
        Use searchengine to search specified keyword.
        input:
            keyword: the keyword to search
            size: the length of search result
        '''
        size = size if size else self.size
        pageSize = self.config['param']['pgsize']['max']
        pages = size / pageSize

        params = self.defaultParam
        params.update({self.config['param']['query']: keyword})
        params.update({self.config['param']['pgsize']['key']: pageSize})

        result = list()
        for p in xrange(pages+1):
            params.update({self.config['param']['pgnum']: p*pageSize})

            for item in self._search(params):
                yield item


    def _search(self, params):
        '''
        Request with specified param, parse the reponse html document.
        input:
            params: the query params
        output:
            return the search result, result format is:
                [[titel,url,brief-information],[...]...]
        '''
        for i in xrange(self.retry):
            #use delay time and random user-agent to bypass IP restrict policy
            delayTime = random.randint(1,3)
            time.sleep(delayTime)

            userAgent = self.userAgents[random.randint(0,len(self.userAgents))-1]
            xforward = "192.168.3." + str(random.randint(1,255))

            headers = {"User-Agent":userAgent, "X-Forward-For":xforward, "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3"}
            try:
                reponse = requests.get(self.url, headers=headers, params=params)
            except Exception as error:
                continue

            if self.findSignature in reponse.text:
                for item in self._parseHtml(reponse.text):
                    yield item
                break
            elif self.notFindSignature in reponse.text:
                raise StopIteration()
        else:
            raise StopIteration()


    def _parseHtml(self, document):
        '''
        Parse html return the formated result. Should be redefine in subclass.
        input:
            the html document
        output:
            return the formated search result, result format is:
                [[titel,url,brief-information],[...]...]
        '''
        return list()



class Baidu(SearchEngine):
    '''
    Baidu search engine.
    input:
        size: specified the amount of the result
    example:
        baidu=Baidu()
        baidu.search("site:xxx.com password.txt")
    '''
    def __init__(self, size=200):
        super(Baidu,self).__init__("baidu",size)
        self.findSignature = "class=f"
        self.notFindSignature = "noresult.html"


    def _parseHtml(self, document):
        document = BeautifulSoup(document)
        attrs={"class":"f"}
        relist = document.findAll("td", attrs=attrs)
        if not relist:
            raise StopIteration()

        for line in relist:
            title = "".join([x.string for x in line.a.font.contents])
            url = line.a["href"]
            briefDoc = line.a.nextSibling.nextSibling.contents
            brief = briefDoc[0].string + (briefDoc[1].string if briefDoc[1].string else "")
            yield Dict(title=title, url=url, brief=brief)


class Bing(SearchEngine):
    '''
    Bing search engine.
    input:
        size: specified the amount of the result
    example:
        bing=Bing()
        bing.search("site:xxx.com password.txt")
    '''
    def __init__(self, size=200):
        super(Bing,self).__init__("bing",size)
        self.findSignature = 'class="b_algo"'
        self.notFindSignature = 'class="b_no"'

    def _parseHtml(self, document):
        document = BeautifulSoup(document)
        attrs = {"class":"b_algo"}
        relist = document.findAll("li", attrs=attrs)
        if not relist:
            raise StopIteration()

        for line in relist:
            title = "".join([x.string for x in line.h2.a.contents])
            url = line.h2.a["href"]
            brief = "".join([x.string for x in line.contents[1].p.contents])
            yield Dict(title=title, url=url, brief=brief)


