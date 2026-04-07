from flask import Flask, request, jsonify, Response
from flask_restful import Resource, Api
import json
import os
import random
import redis

import json, requests
from multiprocessing import Process
import time
from datetime import datetime
import hashlib

import base64
import datetime

from flask import render_template
import werkzeug.serving
import ssl


app = Flask(__name__)
api = Api(app)


debugging=False
if(os.environ.get("SCONE_LOG") == "DEBUG"): debugging=True
elif(os.environ.get("SCONE_LOG") == "TRACE"): debugging=True
elif(os.environ.get("CIAM_LOG") == "DEBUG"): debugging=True
elif(os.environ.get("CIAM_LOG") == "TRACE"): debugging=True

if True == debugging:
    print('Flask is running in DEBUG mode')

ephemeraltoken=False
if(os.environ.get("CIAM_EPHEMERAL_SHARE") == "1"): ephemeraltoken=True

# Setup redis instance.
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
db = redis.Redis(
  host=REDIS_HOST,
  port=REDIS_PORT,
  ssl=True,
  ssl_keyfile='/tls/redis-client.key',
  ssl_certfile='/tls/redis-client.crt',
  ssl_cert_reqs="required",
  ssl_ca_certs='/tls/redis-ca.crt')

# Test connection to redis (break if the connection fails).
db.info()


def addusertokenkey(arr):
    """@parameters: array, where [0] is username and [1] is access token
    \nAdd this key to Redis database, representing the user and the corresponding access token
    \nCan be used to enforce control, depending on the use case
    \nSets up expiration to rigid 90 seconds, currently
    \n• Key: token_%username%__%access token hash%
    \n• Value: access token
    """
    user = arr[0]
    password = arr[1]
    expire = arr[2]
    tokenhash=hashlib.sha256(password.encode("utf-8")).hexdigest()
    db.set("tokens_"+ user+ "__"+ tokenhash, password)
    db.expire(name="tokens_"+ user+ "__"+ tokenhash, time=expire)


def parseuserpassword(arr):
    """
    Validates whether the client provided the appropriate CIAM user and its corresponding
    secret (token or password - token, in this case)
    """
    ciam_user_id = ""
    ciam_user_secret = ""
    try:
        ciam_user_id=str(arr[0])
        ciam_user_secret=str(arr[1])
    except Exception as e:
        print(e)
        raise Exception("PRECHECK:problem trying to get fields 'ciamuserid' and 'ciamusersecret' from request. "+str(e))

    if False == ciam_user_id.isalnum():
        raise Exception ("problem trying to get field 'ciamuserid' from request")
    if len(ciam_user_secret) == 0:
        raise Exception("problem trying to get field 'ciamusersecret' from request")
    return [ciam_user_id, ciam_user_secret]


def checktokenvalidity(arr):
    """
    Validates against the Keycloak assigned server whether the access token is valid
    """
    ciam_user_id=arr[0]
    ciam_user_secret=arr[1]
    exit_code=1
    response = app.response_class(response=json.dumps({"error": "failed to process access token:check the endpoints, logs and overall system state"}),
                                status=503,
                                mimetype='application/json')

    for ct in range(0, 4):
        sessionkeycloakciam = requests.Session()
        sessionkeycloakciam.verify = '/tls/keycloak-ca.crt'
        sessionkeycloakciam.cert=('/tls/keycli.pem', '/tls/keycli-key.pem')
        s_output = ""
        s_errput = ""
        exit_code = 0
        if(debugging):
            p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. ciam_user_secret:'+ciam_user_secret,))
            p.start()
            p.join()
            p.close()

        try:
            payload = ciam_user_secret.split(".")[1]
            j_payload = json.loads(base64.urlsafe_b64decode(payload + '=' * (4 - len(payload) % 4)).decode('utf-8'))
            if(debugging):
                p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'.j_payload:'+str(j_payload),))
                p.start()
                p.join()
                p.close()
            if('chart-flask' != str(j_payload['azp'])):
                if(debugging):
                    p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. payload:'+str(j_payload['azp'])+'. is not "chart-flask". ABORT',))
                    p.start()
                    p.join()
                    p.close()
                raise Exception('{"error": "invalid token"}')
            scopes=str(j_payload['scope']).split(' ')
            hasscope=False
            for scope in scopes:
                if(scope == 'charts'):
                    hasscope=True
                    break
            if(False == hasscope):
                if(debugging):
                    p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. payload:'+str(j_payload['scope'])+'. has not "charts". ABORT',))
                    p.start()
                    p.join()
                    p.close()
                raise Exception('{"error": "invalid token"}')

            response = sessionkeycloakciam.get("https://keycloak.ciam:8443/realms/enchiridion/protocol/openid-connect/userinfo", headers={"Authorization":"Bearer "+ciam_user_secret})
            if(response.status_code != 200):
                exit_code = response.status_code
                if(debugging):
                    p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. retcode:'+str(exit_code),))
                    p.start()
                    p.join()
                    p.close()

            s_output = response.json()
            s_errput = response.json()
            if(debugging):
                p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. s_output=response.json',))
                p.start()
                p.join()
                p.close()
                p = Process(target=print, args=(s_output,))
                p.start()
                p.join()
                p.close()

            s_output = str(s_output).replace("'", '"').replace(r"True","true").replace(r"False","false")
            s_errput = str(s_errput).replace("'", '"').replace(r"True","true").replace(r"False","false")
            if(debugging):
                p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. retcode:'+str(exit_code),))
                p.start()
                p.join()
                p.close()
                p = Process(target=print, args=(s_output,))
                p.start()
                p.join()
                p.close()
        except Exception as errcnx:
            exit_code = 1
            s_output = errcnx #.strerror
            s_errput = errcnx #.strerror
            if(debugging):
                p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. retcode:'+str(exit_code),))
                p.start()
                p.join()
                p.close()
                p = Process(target=print, args=(s_output,))
                p.start()
                p.join()
                p.close()
        #########

        if exit_code != 0:
            response = app.response_class(response=json.dumps(s_output.replace("\n", "")),
                                        status=exit_code,
                                        mimetype='application/json')
            time.sleep(ct+1)
            if ct == 3:
                break

        else:
            if(debugging):
                p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. retcode:'+str(exit_code)+'. len(s_output):'+str(len(s_output))+'. Popen.stdout:'+s_output.replace("\n", " "),))
                p.start()
                p.join()
                p.close()
            body=json.loads(s_output)

            if body["preferred_username"] == ciam_user_id:
                header = ciam_user_secret.split(".")[0]
                payload = ciam_user_secret.split(".")[1]
                signature = ciam_user_secret.split(".")[2]
                j_header = json.loads(base64.urlsafe_b64decode(header + '=' * (4 - len(header) % 4)).decode('utf-8'))
                j_payload = json.loads(base64.urlsafe_b64decode(payload + '=' * (4 - len(payload) % 4)).decode('utf-8'))
                body["timeofissuing"] = j_payload["iat"]
                body["timeofexpiring"] = j_payload["exp"]
                body["timeofvalidation"] = int(datetime.datetime.timestamp(datetime.datetime.now()))
                return [exit_code, body]
            else:
                response = app.response_class(response=json.dumps({"error": "failed to check access token:invalid token:different proprietary"}),
                                            status=403,
                                            mimetype='application/json')
                exit_code=2
                break
    return [exit_code, response]


class Patient(Resource):
    def get(self, patient_id):
        if(debugging):
            p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. request.environ:',))
            p.start()
            p.join()
            p.close()
            p = Process(target=print, args=(request.environ,))
            p.start()
            p.join()
            p.close()
            p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. request.headers:',))
            p.start()
            p.join()
            p.close()
            p = Process(target=print, args=(request.headers,))
            p.start()
            p.join()
            p.close()

        patient_data = db.get(patient_id)
        if patient_data is not None:
            decoded_data = json.loads(patient_data.decode('utf-8'))
            decoded_data["id"] = patient_id
            return jsonify(decoded_data)
        response = app.response_class(response=json.dumps({"error": "unknown patient_id"}),
                                    status=404,
                                    mimetype='application/json')
        return response

    def post(self, patient_id):
        if(debugging):
            p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. request.environ:',))
            p.start()
            p.join()
            p.close()
            p = Process(target=print, args=(request.environ,))
            p.start()
            p.join()
            p.close()
            p = Process(target=print, args=('[DBG][PID:'+str(os.getpid())+'. request.headers:',))
            p.start()
            p.join()
            p.close()
            p = Process(target=print, args=(request.headers,))
            p.start()
            p.join()
            p.close()

        ciam_user_id = ""
        ciam_user_secret = ""
        try:
            (ciam_user_id, ciam_user_secret) = parseuserpassword([request.form["ciamuserid"], request.form["ciamusersecret"]])
        except Exception as e:
            response = app.response_class(response=json.dumps({"error": str(e)}),
                                        status=400,
                                        mimetype='application/json')
            return response

        try:
            (exit_code, response) = checktokenvalidity([ciam_user_id, ciam_user_secret])
            if exit_code != 0:
                return response
        except Exception as e:
            response = app.response_class(response=json.dumps({"error": "failed check token execution: "+str(e)}),
                                        status=500,
                                        mimetype='application/json')
            return response

        """
        # two permission modes are accepted:
        # 1) lenient: the full time lenght is set up: from time of issuing to the time of expiring of the access token
        # 1) rigid: the partial time lenght is set up: from time of issuing to the time of validation of the access token
        # *) ** otherwise the time length is set up to 90 seconds
        """
        # permissionmode="lenient"
        permissionmode="rigid"
        expireinseconds = 0
        timeofissuing = response["timeofissuing"]
        timeofexpiring = response["timeofexpiring"]
        timeofvalidation = response["timeofvalidation"]
        if permissionmode == "rigid":
            expireinseconds = timeofexpiring-timeofvalidation
        elif permissionmode == "lenient":
            expireinseconds = timeofexpiring-timeofissuing
        else:
            expireinseconds = 90

        # database
        if db.exists(patient_id):
            response = app.response_class(response=json.dumps({"error": "already exists"}),
                                        status=403,
                                        mimetype='application/json')
            return response
        else:
            if(ephemeraltoken):
                addusertokenkey([ciam_user_id, ciam_user_secret, expireinseconds])

            # convert patient data to binary.
            patient_data = json.dumps({
            "fname": request.form['fname'],
            "lname": request.form['lname'],
            "address": request.form['address'],
            "city": request.form['city'],
            "state": request.form['state'],
            "ssn": request.form['ssn'],
            "email": request.form['email'],
            "dob": request.form['dob'],
            "contactphone": request.form['contactphone'],
            "drugallergies": request.form['drugallergies'],
            "preexistingconditions": request.form['preexistingconditions'],
            "dateadmitted": request.form['dateadmitted'],
            "insurancedetails": request.form['insurancedetails'],
            "score": random.random()
            }).encode('utf-8')
            try:
                db.set(patient_id, patient_data)
            except Exception as e:
                print(e)
                return Response({"error": "internal server error"}, status=500, mimetype='application/json')
            patient_data = json.loads(patient_data.decode('utf-8'))
            patient_data["id"] = patient_id
            return jsonify(patient_data)


class Score(Resource):
    def get(self, patient_id):
        patient_data = db.get(patient_id)
        if patient_data is not None:
            score = json.loads(patient_data.decode('utf-8'))["score"]
            return jsonify({"id": patient_id, "score": score})
        response = app.response_class(response=json.dumps({"error": "unknown patient"}),
                                    status=404,
                                    mimetype='application/json')
        return response

api.add_resource(Patient, '/patient/<string:patient_id>')
api.add_resource(Score, '/score/<string:patient_id>')


if __name__ == '__main__':
    app.debug = False
    my_ssl_context = ssl.create_default_context( purpose=ssl.Purpose.CLIENT_AUTH, cafile="/tls/flask-ca.crt")
    my_ssl_context.load_cert_chain( certfile="/tls/flask-server.crt", keyfile="/tls/flask-server.key")
    my_ssl_context.verify_mode = ssl.CERT_REQUIRED
    app.run(host='0.0.0.0', port=4996, threaded=True, ssl_context=(my_ssl_context))
