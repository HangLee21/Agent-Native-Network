#ifndef TEST_CJSON_H
#define TEST_CJSON_H
typedef struct cJSON {double valuedouble;char*valuestring;} cJSON;
cJSON*cJSON_GetObjectItemCaseSensitive(cJSON*,const char*);
int cJSON_IsNumber(cJSON*);int cJSON_IsString(cJSON*);int cJSON_IsBool(cJSON*);int cJSON_IsTrue(cJSON*);
cJSON*cJSON_CreateObject(void);cJSON*cJSON_AddObjectToObject(cJSON*,const char*);
void cJSON_AddStringToObject(cJSON*,const char*,const char*);void cJSON_AddNumberToObject(cJSON*,const char*,double);void cJSON_AddBoolToObject(cJSON*,const char*,int);void cJSON_AddNullToObject(cJSON*,const char*);
#endif
