def fetch_youtube_data(api_key, video_id):
    import requests
    url = f'https://www.googleapis.com/youtube/v3/videos?id={video_id}&key={api_key}&part=snippet,contentDetails,statistics'
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception('Error fetching data from YouTube API')

if __name__ == '__main__':
    API_KEY = 'YOUR_API_KEY'
    VIDEO_ID = 'YOUR_VIDEO_ID'
    data = fetch_youtube_data(API_KEY, VIDEO_ID)
    print(data)