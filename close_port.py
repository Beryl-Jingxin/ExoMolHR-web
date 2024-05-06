# -*-coding: UTF-8 -*-
import os


def killport(port):
    command = '''kill -9 $(netstat -nlp | grep :'''+str(port)+''' | awk '{print $7}' | awk -F"/" '{print $1}')'''
    os.system(command)
    
    
if __name__ == '__main__':
    port=8888
    killport(port)
    
