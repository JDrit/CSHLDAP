#!/usr/bin/python
# written for python 2.7, tested on 2.6

import ldap as pyldap
import ldap.sasl as sasl
import ldap.modlist
import re
from datetime import datetime, date
from copy import deepcopy

class CSHLDAP:
    def __init__(self, user, password, host='ldaps://ldap.csh.rit.edu:636', \
            base='ou=Users,dc=csh,dc=rit,dc=edu', bind='ou=Apps,dc=csh,dc=rit,dc=edu', app = False):
        self.host = host
        self.base = base
        self.users = 'ou=Users,dc=csh,dc=rit,dc=edu'
        self.groups = 'ou=Groups,dc=csh,dc=rit,dc=edu'
        self.committees = 'ou=Committees,dc=csh,dc=rit,dc=edu'
        self.ldap = pyldap.initialize(host)

        if app:
            self.ldap.simple_bind('cn='+user+','+bind, password)
        else:
            try:
                auth = sasl.gssapi("")

                self.ldap.sasl_interactive_bind_s("", auth)
            	self.ldap.set_option(pyldap.OPT_DEBUG_LEVEL,0)
            except pyldap.LDAPError, e:
            	print 'Are you sure you\'ve run kinit?'
            	print e

    def members(self, uid="*", objects=False):
        """ members() issues an ldap query for all users, and returns a dict
            for each matching entry. This can be quite slow, and takes roughly
            3s to complete. You may optionally restrict the scope by specifying
            a uid, which is roughly equivalent to a search(uid='foo')
        """
        entries = self.search(uid='*')
        if objects:
            return self.memberObjects(entries)
        result = []
        for entry in entries:
            result.append(entry[1])
        return result

    def member(self, user, objects=False):
        """ Returns a user as a dict of attributes
        """
        try:
            member = self.search(uid=user, objects=objects)[0]
        except IndexError:
            return None
        if objects:
            return member
        return member[1]

    def eboard(self, objects=False):
        """ Returns a list of eboard members formatted as a search
            inserts an extra ['commmittee'] attribute
        """
        # self.committee used as base because that's where eboard
        # info is kept
        committees = self.search(base = self.committees, cn='*')
        directors = []
        for committee in committees:
            for head in committee[1]['head']:
                director = self.search(dn=head)[0]
                director[1]['committee'] = committee[1]['cn'][0]
                directors.append(director)
        if objects:
            return self.memberObjects(directors)
        return directors

    def group(self, group_cn, objects=False):
        members = self.search(base=self.groups,cn=group_cn)
        if len(members) == 0:
            return members
        else:
            member_dns = members[0][1]['member']
        members = []
        for member_dn in member_dns:
            members.append(self.search(dn=member_dn)[0])
        if objects:
            return self.memberObjects(members)
        return members

    def getGroups(self, member_dn):
        searchResult = self.search(base=self.groups, member=member_dn)
        if len(searchResult) == 0: return []

        groupList = []
        for group in searchResult:
            groupList.append(group[1]['cn'][0])
        return groupList

    def drinkAdmins(self, objects=False):
        """ Returns a list of drink admins uids
        """
        admins = self.group('drink', objects=objects)
        return admins

    def rtps(self, objects=False):
        rtps = self.group('rtp', objects=objects)
        return rtps

    def trimResult(self, result):
        return [x[1] for x in result]

    def search( self, base=False, trim=False, objects=False, **kwargs ):
        """ Returns matching entries for search in ldap
            structured as [(dn, {attributes})]
            UNLESS searching by dn, in which case the first match
            is returned
        """
        scope = pyldap.SCOPE_SUBTREE
        if not base:
            base = self.users

        filterstr =''
        for key, value in kwargs.iteritems():
            filterstr += '({0}={1})'.format(key,value)
            if key == 'dn':
                filterstr = '(objectClass=*)'
                base = value
                scope = pyldap.SCOPE_BASE
                break

        if len(kwargs) > 1:
            filterstr = '(&'+filterstr+')'

        result = self.ldap.search_s(base, pyldap.SCOPE_SUBTREE, filterstr, ['*','+'])
        if base == self.users:
            for member in result:
                groups = self.getGroups(member[0])
                member[1]['groups'] = groups
                if 'eboard' in member[1]['groups']:
                    member[1]['committee'] = self.search(base=self.committees, \
                           head=member[0])[0][1]['cn'][0]
        if objects:
            return self.memberObjects(result)
        finalResult = self.trimResult(result) if trim else result
        return finalResult

    def modify( self, uid, base=False, **kwargs ):
        if not base:
            base = self.users
        dn = 'uid='+uid+',ou=Users,dc=csh,dc=rit,dc=edu'
        old_attrs = self.member(uid)
        new_attrs = deepcopy(old_attrs)

        for field, value in kwargs.iteritems():
            if field in old_attrs:
                new_attrs[field] = [str(value)]
        modlist = pyldap.modlist.modifyModlist(old_attrs, new_attrs)

        self.ldap.modify_s(dn, modlist)

    def memberObjects( self, searchResults ):
        results = []
        for result in searchResults:
            newMember = Member(result, ldap=self)
            results.append(newMember)
        return results

class Member(object):
    def __init__(self, member, ldap=None):
        if len(member) < 2:
            self.memberDict = {}
        else:
            self.memberDict = member[1]
        self.ldap = ldap

    def __getattr__(self, attribute):
        if attribute in ("memberDict", "ldap"):
            return object.__getattribute__(self, attribute)
        try:
            attributes = self.memberDict[attribute]
            if len(attributes) == 1:
                attribute = attributes[0]
                if attribute.isdigit():
                    return int(attribute)
                return attribute
            return attributes
        except (KeyError, IndexError):
            return None

    def __setattr__(self, attribute, value):
        if attribute in ("memberDict", "ldap"):
            object.__setattr__(self, attribute, value)
            return
        kwargs = {attribute : value}
        self.ldap.modify(uid=self.uid, **kwargs)
        self.memberDict[attribute] = value

    def fields(self):
        return self.memberDict.keys()

    def isActive(self):
        return bool(self.active)

    def isAlumni(self):
        return bool(self.alumni)

    def isDrinkAdmin(self):
        return bool(self.drinkAdmin)

    def isOnFloor(self):
        return bool(self.onfloor)

    def isEboard(self):
        return 'eboard' in self.groups

    def isRTP(self):
        return 'rtp' in self.groups

    def isBirthday(self):
        birthday = self.birthdate()
        today = date.today()
        return (birthday.month == today.month and
                birthday.day == today.day)

    def birthdate(self):
        if not self.birthday:
            return None
        return dateFromLDAPTimestamp(self.birthday)

    def joindate(self):
        if not self.memberSince:
            return None
        joined = self.memberSince
        return dateFromLDAPTimestamp(joined)

    def age(self):
        if not self.birthdate():
            return -1
        adjuster = 0
        today = date.today()
        birthday = self.birthdate()
        if today.month == birthday.month:
            if today.day < birthday.day:
                adjuster -= 1
        elif today.month < birthday.month:
            adjuster -= 1
        return (today.year - birthday.year) + adjuster

    def reload(self):
        if not self.ldap:
            return
        self.memberDict = self.ldap.member(self.uid)

def dateFromLDAPTimestamp(timestamp):
    # only check the first 12 characters: YYYYmmddHHMM
    numberOfCharacters = len("YYYYmmddHHMM")
    timestamp = timestamp[:numberOfCharacters]
    day = datetime.strptime(timestamp, '%Y%m%d%H%M')
    return date(year=day.year, month=day.month, day=day.day)
