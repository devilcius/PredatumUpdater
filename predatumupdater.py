# -*- coding: utf_8 -*-
#from time import sleep, clock, time
import urllib2
from urllib2 import URLError, HTTPError
import os.path
import ConfigParser
import urllib
import cookielib
from httplib import BadStatusLine
import mutagen
# important:
# modified flac.py file to get flac bitrate
# (must be copy from ./ to /usr/local/lib/python2.7/dist-packages/mutagen/
# or ~/.local/lib/python2.7/site-packages)
from mutagen.flac import FLAC
from mp3 import MP3 #modified file to get lame_preset
from mutagen.oggvorbis import OggVorbis
import os
from sqlite3 import *
import json as simplejson
import re
from time import sleep

#elapsedTime = 0;

class Error(Exception):
    """Base class for exceptions in this module."""
    pass


class DataBase():

    def __init__(self):
        self.conn = connect('music.db')
        self.curs = self.conn.cursor()
        self.createLocalTable()

    def createLocalTable(self):
        # Creates MP3 table if not exists
        self.curs.execute('''create table if not exists tracks
          (id integer primary key, folder_path text, file_name text, artist text, title text,
          album text, genre text, year int, track integer, file_size integer, file_date text, track_duration integer,
          bitrate integer, quality text, lame_encoded integer, file_type text, comment text, rating integer, pred_updated integer)''')  # lint:ok

    def checkRecordExists(self, file_name, file_size, album):

        return self.conn.execute("select id from tracks where file_name = ? and file_size = ? and album = ?",(file_name, file_size, album)).fetchone() != None


    def updateDB(self,folder_path,file_name, artist, title, album, genre, year, track, file_size, file_date, track_duration, bitrate, quality, lame_encoded, file_type, comment, rating):

        if self.checkRecordExists(file_name, file_size, album):
            print "file %s from %s exists, skipping..." % (file_name, artist)
        else:
            self.curs.execute("insert into tracks (folder_path, file_name, artist, title, album, genre, year, track, file_size, file_date,\
                                track_duration, bitrate, quality, lame_encoded, file_type, comment, rating, pred_updated) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0 )", \
                              (folder_path, file_name, artist, title, album, genre, year, track, file_size, file_date, \
                               track_duration, bitrate, quality, lame_encoded, file_type, comment, rating))
            print "inserting %s to local db" % file_name

        self.conn.commit()

    def getFolderNotPostedToSite(self):
        return self.curs.execute("select folder_path, file_name, artist, title, album, genre, year, \
                                track, file_size, file_date, track_duration, bitrate, quality, \
                                lame_encoded, file_type, comment, rating \
                                from tracks \
                                where folder_path = (select folder_path from tracks where pred_updated = 0 limit 1) \
                                order by pred_updated asc, album"
                                )


    def setRecordUpdatedInPredatum(self, file_name, file_size):
        try:
            self.conn.execute("update tracks set pred_updated = 1 where file_name = ? and file_size = ?",(file_name, int(file_size)))
            self.conn.commit()
            return True
        except IntegrityError:
            return False


    def folderAlreadyChecked(self, folder_name):

        return self.conn.execute("select id from tracks where folder_path = ? ",(folder_name,)).fetchone() != None

class AudioFile():


    def getAudioFileData(self, file):
        audioFileData = {}
        audioFile = None
        fileExtension = getFileExtension(file).lower()
        audioFileData['tracknumber'] = audioFileData['file_date'] = audioFileData['artist'] = audioFileData['comment'] = audioFileData['title'] = audioFileData['genre'] = audioFileData['album'] = [None]
        audioFileData['file_type'] = audioFileData['playtime'] = audioFileData['size'] = audioFileData['quality'] = audioFileData['bitrate'] = None
        audioFileData['lame_encoded'] = 0
        audioFileData['date'] = audioFileData['rating'] = [0]

        try:
            audioFileData['size'] = os.path.getsize(file)
            audioFileData['file_type'] = fileExtension[1:].upper()
            t = os.path.getctime(file)
            audioFileData['file_date'] = datetime.datetime.fromtimestamp(t).strftime("%Y/%m/%d %H:%M:%S")
            #set metadata
            for tag, value in mutagen.File(file, easy=True).items():
                # fix year tag
                if tag == 'date':
                    try:
                        regyear = re.compile('[1-2][0-9][0-9][0-9]')
                        audioFileData['date'] = regyear.search(audioFileData["date"][0]).group(0)
                    except:
                        audioFileData['date'] = [0]
                #check for empty arrays
                if len(value) < 1:
                    value = [None]

                audioFileData[tag] = value

            #set audio info
            if fileExtension == '.mp3':
                audioFile = MP3(file)
                if audioFile.info.lame_info:
                    audioFileData['lame_encoded'] = 1
                    audioFileData['quality'] = audioFile.info.lame_preset
            elif fileExtension == '.flac':
                audioFile = FLAC(file)
                audioFileData['quality'] = 'lossless'
            else:
                audioFile = OggVorbis(file)

            audioFileData['playtime'] = int(audioFile.info.length)
            audioFileData['bitrate'] = int(audioFile.info.bitrate/1000)

            return audioFileData

        except Exception, msg:
            print "error retrieving audio data from %s: %s" % (file,msg)
            return None



class Scan():


    def __init__(self, recheck):
        self.supportedMusicFileExtensions = ['.mp3','.flac','.ogg']
        self.recheckFolders = recheck

        self.db = DataBase();

    def folders(self, rootfolder):
        filecount = 0
        for root, dirs, files in os.walk(rootfolder):
            print "about to check %s" % root
            if self.recheckFolders == '1':
                if self.files(files, root) > 0:
                    filecount = filecount + len(files)
            else:
                folderName = "%s/" % root.decode('utf-8')
                if self.db.folderAlreadyChecked(folderName):
                    print 'folder already checked, skipping'
                else:
                    if self.files(files, root) > 0:
                        filecount = filecount + len(files)


        print "checked %d files" % filecount
        return True

    def files(self, folderfiles, folderpath):
        trackcount = 0
        audioFile = AudioFile()
        currentAlbum = ''

        for file in [f for f in folderfiles]:
            fileExtension = getFileExtension(file).lower()
            if fileExtension in self.supportedMusicFileExtensions:
                audioFileData = audioFile.getAudioFileData(folderpath + "/" + file)
                if audioFileData is not None:
                    if currentAlbum != audioFileData['album'][0]:
                        trackcount = 1
                        currentAlbum = audioFileData['album'][0]
                    else:
                        trackcount = trackcount + 1
                    tracknum = audioFileData['tracknumber'][0]
                    if tracknum is None:
                        tracknum = trackcount

                    #update table
                    self.db.updateDB(str(folderpath + "/").decode("utf-8"), file.decode("utf-8"), \
                        audioFileData['artist'][0], audioFileData['title'][0], \
                        audioFileData['album'][0], audioFileData['genre'][0], \
                        audioFileData['date'][0],  tracknum, audioFileData['size'], \
                        audioFileData['file_date'], audioFileData['playtime'], \
                        audioFileData['bitrate'], audioFileData['quality'], audioFileData['lame_encoded'], \
                        audioFileData['file_type'], audioFileData['comment'][0], audioFileData['rating'][0])

        return trackcount


class Predatum:

    site = "https://predatum.com"
    userAgent = 'predatumupdater [1.0]'

    def __init__(self, user, password):

        self.username = user
        self.password = password
        self.cookieFile = 'predatum_cookie'
        self.setUpCookiesAndUserAgent()
        self.localdb = DataBase()


    def setUpCookiesAndUserAgent(self):

        cookieJar = cookielib.LWPCookieJar()
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookieJar))
        opener.addheaders = [('User-Agent', Predatum.userAgent)]
        urllib2.install_opener(opener)

        self.loadCookiesFromFile(cookieJar)

        try:
            self.authenticate()
            print "using cookie"
        except Error:
            self.getFreshCookies()

    def loadCookiesFromFile(self, cookieJar):
        try:
            cookieJar.load(self.cookieFile)
        except IOError:
            self.authenticate()
            cookieJar.save(self.cookieFile)

    def getFreshCookies(self):
        cookieJar = cookielib.LWPCookieJar()
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookieJar))
        opener.addheaders = [('User-Agent', Predatum.userAgent)]
        urllib2.install_opener(opener)
        self.authenticate()
        cookieJar.save(self.cookieFile)
        print "new cookie created"

    def authenticate(self):
        loginURL = Predatum.site + "/api/user/authenticate"
        data = urllib.urlencode({'email': self.username,
                     'password': self.password,
                     'remember': '1',
                     'submit': 'Submit'})
        try:
            request = urllib2.Request(loginURL, data)
            response = urllib2.urlopen(request)
            self.checkIfAuthenticated(response.read())
        except HTTPError, e:
            print 'The server couldn\'t fulfill the request.'
            print 'Error code: ', e.read()
        except URLError, e:
            print 'We failed to reach a server.'
            print 'Reason: ', e.reason
        except BadStatusLine, e:
            print "the status line can’t be parsed as a valid HTTP/1.0 or 1.1 status line: ", e.line

    def checkIfAuthenticated(self, response):
        json = simplejson.loads(response)
        if (json['error']):
          print 'Login page returned: '  + json['error']
          quit()


    def getAlbumsToPost(self):

        albumsToUpdate = {}
        previousAlbum = currentAlbum = ''
        firstArtist = ''
#        print "quering database to get get album to post at %d" % (time.time() - elapsedTime)
        recordsToUpdate = self.localdb.getFolderNotPostedToSite()
        albumCounter = 0
        trackCounter = 0
        isAlbumVA = False
#        print "album to post returned from database at %d" % (time.time() - elapsedTime)
#        print "preparing dictionary to post"
        for row in recordsToUpdate:
            '''
            folder_path, file_name, artist, title, album,
            genre, year, track, file_size, file_date, track_duration,
            bitrate, quality, lame_encoded, file_type
            '''
            currentAlbum = row[4]
            if trackCounter == 0:
                firstArtist = row[2]

            if currentAlbum != previousAlbum:

                trackCounter = 0
                albumCounter = albumCounter + 1
                albumsToUpdate[albumCounter] = {}
                albumsToUpdate[albumCounter]['name'] = row[4]
                albumsToUpdate[albumCounter]['folder_path'] = row[0]
                albumsToUpdate[albumCounter]['year'] = row[6]
                albumsToUpdate[albumCounter]['is_va'] = isAlbumVA
                albumsToUpdate[albumCounter]['tracks'] = {}

                if previousAlbum != row[4]:
                    previousAlbum = currentAlbum

            albumsToUpdate[albumCounter]['tracks'][trackCounter] = {}
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['artist'] = row[2]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['file_name'] = row[1]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['title'] = row[3]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['genre'] = row[5]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['track'] = row[7]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['file_size'] = row[8]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['file_date'] = row[9]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['duration'] = row[10]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['bitrate'] = row[11]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['quality'] = row[12]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['is_lame_encoded'] = row[13]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['file_type'] = row[14]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['comment'] = row[15]
            albumsToUpdate[albumCounter]['tracks'][trackCounter]['rating'] = row[16]
            if firstArtist != row[2]:
                albumsToUpdate[albumCounter]['is_va'] = True

            trackCounter = trackCounter + 1
#        print "dictionary created at %d" % (time.time() - elapsedTime)
        return albumsToUpdate


    def updateSite(self):

        headers = {"Content-type": "application/json; charset=utf-8",
                    "Accept": "*/*"}


        albumstopost = self.getAlbumsToPost().items()

#        print "ready to post to predatum at %d" % (time.time() - elapsedTime)
        if len(albumstopost) < 1:
            print "site up to date"

        for index, album in albumstopost:
            params = simplejson.dumps(album)
            responsebody = None
            try:
                print "about to insert %s from %s" % (album['name'], album['folder_path'])
                request = urllib2.Request(Predatum.site + "/api/release", params, headers)
                response = urllib2.urlopen(request)
                responsebody = response.read()

                json = simplejson.loads(responsebody)
                if json['error'] != 1:
                    self.setAlbumSubmitted(album)
                    print json['message']
#                    print "posted ok at %d" % (time.time() - elapsedTime)
                else:
                    print json['message']
                    quit()
            except HTTPError, e:
                print 'The server couldn\'t fulfill the request.'
                print 'Error code: ', e.read()
                quit()
            except URLError, e:
                print 'We failed to reach a server.'
                print 'Reason: ', e.reason
                quit()
            except BadStatusLine, e:
                print "the status line can’t be parsed as a valid HTTP/1.0 or 1.1 status line: ", e.line
                quit()
            except ValueError, e:
                print "error processing json, %s:\n%s" % (e, responsebody)
                quit()
            except Exception, msg:
                print "unknown error: %s.\nServer response: %s" % (msg, responsebody)
                quit()


            return True


    def setAlbumSubmitted(self, album):
        for index, track in album['tracks'].items():
            self.localdb.setRecordUpdatedInPredatum(track['file_name'], track['file_size']);


def getFileExtension(filename):
    return os.path.splitext(filename)[1]




def main():
    config = ConfigParser.ConfigParser()
    config.read('predatumupdater.cfg')
    scan = Scan(config.get("options", "recheck"))
    scan.folders(config.get("options","musicdir"))

    pred = Predatum(config.get("predatum", "username"), config.get("predatum", "password"))
    while pred.updateSite():
     	sleep(0.1) #prevents CPU going nuts



if __name__ == "__main__":
    main()
    #print "Module to update local and remote predatum db"
