from google import genai

# Ricordati di incollare la tua vera API KEY qui
client = genai.Client(api_key="AIzaSyD3wjz8-vCJREY-u4X4LKEH1J-SHwScgag")

print("Ecco TUTTI i modelli disponibili per la tua chiave:")
for m in client.models.list():
    print(m.name)